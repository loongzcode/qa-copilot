"""自动化任务提交、取消和 Worker 执行编排。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from time import monotonic

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.constants import (
    AutomationDefinitionStatus,
    AutomationExecutionStatus,
    OutboxAggregateType,
    OutboxEventType,
    TestEnvironmentType,
)
from app.exceptions import BadRequestException, ConflictException, ForbiddenException, NotFoundException
from app.mappers.automation_execution_tasks import automation_execution_report_to_vo, automation_execution_task_to_vo
from app.models import AutomationExecutionTask, User
from app.repositories.automation_execution_tasks_repository import AutomationExecutionTasksRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.dto.automation_execution_tasks import AutomationExecutionCreateDTO
from app.schemas.vo.automation_execution_tasks import AutomationExecutionReportVO, AutomationExecutionTaskVO
from app.services.test_environments_api_service import TestEnvironmentsApiService

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AutomationExecutionService:
    """保证只有审批定义能可靠入队，并在 Worker 中受控执行 Pytest 子进程。

    功能：提供列表、提交、取消和后台执行四个业务入口。
    作用：API 使用前三个入口；Celery Worker 使用 execute，共享同一任务状态机。
    为什么用它：状态转换集中后，API 和 Worker 不会各自解释 PENDING/RUNNING；
    事务性发件箱保证数据库任务与待发布消息一起提交，消费者用原子领取保证幂等。
    """

    def __init__(
        self,
        repository: AutomationExecutionTasksRepository,
        project_repository: TestProjectsRepository,
        outbox_repository: OutboxEventRepository,
        environment_service: TestEnvironmentsApiService,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.outbox_repository = outbox_repository
        self.environment_service = environment_service

    async def _require_project(self, project_id: int, current_user: User) -> None:
        """统一校验项目存在且当前用户是负责人、成员或超级管理员。"""
        if await self.project_repository.get_accessible_project(project_id, current_user) is None:
            raise NotFoundException("项目不存在或无权访问")

    async def list_tasks(
        self,
        project_id: int,
        current_user: User,
        status: AutomationExecutionStatus | None,
        current: int,
        size: int,
    ) -> tuple[list[AutomationExecutionTaskVO], int]:
        """分页返回项目执行任务，供前端轮询状态。"""
        await self._require_project(project_id, current_user)
        records, total = await self.repository.list_tasks(project_id, status, current, size)
        return [automation_execution_task_to_vo(record) for record in records], total

    async def get_report(
        self,
        project_id: int,
        task_id: int,
        current_user: User,
    ) -> AutomationExecutionReportVO:
        """返回一次任务的汇总和逐步骤脱敏结果。"""
        await self._require_project(project_id, current_user)
        task, steps = await self.repository.get_report(project_id, task_id)
        if task is None:
            raise NotFoundException("自动化执行任务不存在")
        return automation_execution_report_to_vo(task, steps)

    async def submit_task(
        self,
        project_id: int,
        payload: AutomationExecutionCreateDTO,
        current_user: User,
    ) -> AutomationExecutionTaskVO:
        """在同一 PostgreSQL 事务中保存任务和待发布事件。

        功能：校验定义、环境和非生产边界，创建 PENDING 任务及发件箱事件。
        作用：API 返回后，Celery Beat 发布器会把事件可靠发送到 automation-execution 队列。
        为什么用它：先提交任务再直接发 Redis 存在崩溃空窗；事务性发件箱使二者
        要么一起写入数据库，要么一起回滚，发布失败还能按已有策略重试。
        """
        await self._require_project(project_id, current_user)
        definition, environment = await self.repository.get_submission_assets(
            project_id,
            payload.definition_id,
            payload.environment_id,
        )
        if definition is None:
            raise NotFoundException("自动化定义不存在")
        if definition.status != AutomationDefinitionStatus.APPROVED.value:
            raise BadRequestException("只有已审批自动化定义可以执行")
        if environment is None:
            raise NotFoundException("测试环境不存在")
        if not environment.enabled:
            raise BadRequestException("测试环境已停用")
        if environment.environment_type == TestEnvironmentType.PRODUCTION.value:
            raise ForbiddenException("自动化执行器禁止连接生产环境")

        task = AutomationExecutionTask(
            project_id=project_id,
            definition_id=definition.id,
            environment_id=environment.id,
            timeout_seconds=payload.timeout_seconds,
            definition_hash=definition.definition_hash,
            environment_updated_at=environment.updated_at,
            requested_by=current_user.id,
        )
        self.repository.add(task)
        await self.repository.flush()
        self.outbox_repository.add_pending_event(
            event_type=OutboxEventType.AUTOMATION_EXECUTION.value,
            aggregate_type=OutboxAggregateType.AUTOMATION_EXECUTION.value,
            aggregate_id=task.id,
            payload={"project_id": project_id, "execution_task_id": task.id},
        )
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("该定义已有等待或运行中的执行任务") from exc
        saved = await self.repository.get_task(project_id, task.id)
        if saved is None:
            raise RuntimeError("执行任务提交后无法读取")
        return automation_execution_task_to_vo(saved)

    async def cancel_task(
        self,
        project_id: int,
        task_id: int,
        current_user: User,
    ) -> AutomationExecutionTaskVO:
        """请求取消等待或运行中的任务；最终任务不能重复取消。"""
        await self._require_project(project_id, current_user)
        resulting_status = await self.repository.request_cancel(project_id, task_id)
        if resulting_status is None:
            raise NotFoundException("自动化执行任务不存在")
        if resulting_status not in {
            AutomationExecutionStatus.CANCELLED.value,
            AutomationExecutionStatus.CANCEL_REQUESTED.value,
        }:
            raise ConflictException("任务已进入最终状态，不能取消")
        task = await self.repository.get_task(project_id, task_id)
        if task is None:
            raise NotFoundException("自动化执行任务不存在")
        return automation_execution_task_to_vo(task)

    @staticmethod
    async def _terminate_process(process: asyncio.subprocess.Process) -> None:
        """先温和终止 Pytest 子进程，五秒未退出再强制杀死。"""
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def _run_pytest_subprocess(
        self,
        task: AutomationExecutionTask,
        runtime_payload: dict,
    ) -> tuple[AutomationExecutionStatus, dict, str | None]:
        """启动隔离 Pytest 子进程，并轮询总超时和数据库取消请求。"""
        configured_temp_root = settings.automation_execution_temp_dir
        temp_root = configured_temp_root if configured_temp_root.is_absolute() else PROJECT_ROOT / configured_temp_root
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"qa-auto-{task.id}-", dir=temp_root) as temp_dir:
            input_path = Path(temp_dir) / "input.json"
            output_path = Path(temp_dir) / "output.json"
            input_path.write_text(json.dumps(runtime_payload, ensure_ascii=False), encoding="utf-8")
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-o",
                "addopts=",
                "-p",
                "app.automation.pytest_plugin",
                "app/automation/controlled_pytest_case.py",
                "--automation-input",
                os.fspath(input_path),
                "--automation-output",
                os.fspath(output_path),
                cwd=os.fspath(PROJECT_ROOT),
                env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            started = monotonic()
            while process.returncode is None:
                if await self.repository.is_cancel_requested(task.id):
                    await self._terminate_process(process)
                    return AutomationExecutionStatus.CANCELLED, {}, None
                if monotonic() - started >= task.timeout_seconds:
                    await self._terminate_process(process)
                    return AutomationExecutionStatus.TIMED_OUT, {}, "执行超过任务总超时"
                try:
                    await asyncio.wait_for(process.wait(), timeout=0.5)
                except TimeoutError:
                    continue

            if not output_path.is_file():
                return AutomationExecutionStatus.FAILED, {}, "Pytest 未生成有效执行结论"
            try:
                result = json.loads(output_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return AutomationExecutionStatus.FAILED, {}, "Pytest 执行结论格式错误"
            if process.returncode == 0 and result.get("success") is True:
                return AutomationExecutionStatus.PASSED, result, None
            return AutomationExecutionStatus.FAILED, result, str(result.get("message") or "接口断言未通过")[:500]

    async def execute(self, project_id: int, task_id: int, celery_task_id: str) -> bool:
        """由 Celery Worker 幂等领取任务、复核快照并运行固定 Pytest 入口。"""
        task = await self.repository.claim_task(project_id, task_id, celery_task_id)
        if task is None:
            return False
        try:
            if (
                task.definition.status != AutomationDefinitionStatus.APPROVED.value
                or task.definition.definition_hash != task.definition_hash
            ):
                raise ConflictException("自动化定义已变化或不再处于审批状态")
            if task.environment.updated_at != task.environment_updated_at:
                raise ConflictException("测试环境在任务提交后发生变化，请重新提交")

            runtime_environment = await self.environment_service.build_automation_runtime_environment(
                project_id,
                task.environment_id,
            )
            task.current_stage = "RUNNING_PYTEST"
            task.progress = 30
            await self.repository.commit()
            status, result, error_message = await self._run_pytest_subprocess(
                task,
                {
                    "definition": task.definition.definition,
                    "baseUrl": runtime_environment.base_url,
                    "headers": runtime_environment.headers,
                    "variables": runtime_environment.variables,
                    "maxResponseBytes": settings.automation_response_max_bytes,
                },
            )
            await self._finish_task_with_notification(
                project_id,
                task.id,
                status,
                result_summary={key: value for key, value in result.items() if key != "steps"},
                error_message=error_message,
                step_results=list(result.get("steps") or []),
            )
            return status == AutomationExecutionStatus.PASSED
        except Exception as exc:
            # 不保存异常正文，避免 HTTP 客户端把含凭据的 URL 或请求头带入日志。
            await self.repository.rollback()
            await self._finish_task_with_notification(
                project_id,
                task.id,
                AutomationExecutionStatus.FAILED,
                error_message=f"{type(exc).__name__}: 自动化执行失败",
            )
            return False

    async def _finish_task_with_notification(
        self,
        project_id: int,
        task_id: int,
        status: AutomationExecutionStatus,
        *,
        result_summary: dict | None = None,
        error_message: str | None = None,
        step_results: list[dict] | None = None,
    ) -> bool:
        """在一个 PostgreSQL 事务中保存任务终态和待发送通知事件。

        功能：先更新自动化任务和步骤结果，再新增结果通知发件箱事件，最后统一
        提交。

        作用：这是自动化 Worker 的统一收口点。正常通过、断言失败、超时和执行
        异常都会经过这里，不需要每个分支分别调用通知渠道。

        为什么用它：PostgreSQL 与 Redis 不能共享本地事务。如果先提交终态再
        直接发送 Celery 消息，进程可能在两步之间退出而永久漏通知；事务性发件
        箱先把“需要通知”与任务终态一起保存，再由发布器可靠投递。
        """
        finished = await self.repository.finish_task(
            task_id,
            status,
            result_summary=result_summary,
            error_message=error_message,
            step_results=step_results,
            commit=False,
        )
        if not finished:
            return False
        self.outbox_repository.add_pending_event(
            event_type=OutboxEventType.AUTOMATION_RESULT_NOTIFICATION.value,
            aggregate_type=OutboxAggregateType.AUTOMATION_EXECUTION.value,
            aggregate_id=task_id,
            payload={
                "project_id": project_id,
                "execution_task_id": task_id,
            },
        )
        await self.repository.commit()
        return True
