"""自动化执行任务的数据访问层。"""

from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.core.constants import AutomationExecutionStatus
from app.models import (
    AutomationDefinition,
    AutomationExecutionStepResult,
    AutomationExecutionTask,
    TestEnvironment,
)
from app.models.mixins import utc_now
from app.repositories.base_repository import BaseRepository


class AutomationExecutionTasksRepository(BaseRepository):
    """集中封装任务列表、幂等领取、取消和终态更新 SQL。"""

    @staticmethod
    def _load_options() -> tuple:
        """统一任务转 VO 所需关系，避免不同查询遗漏关联对象。"""
        return (
            selectinload(AutomationExecutionTask.definition),
            selectinload(AutomationExecutionTask.environment),
            selectinload(AutomationExecutionTask.requester),
        )

    async def list_tasks(
        self,
        project_id: int,
        status: AutomationExecutionStatus | None,
        current: int,
        size: int,
    ) -> tuple[list[AutomationExecutionTask], int]:
        """分页查询项目执行任务，最新任务优先。"""
        conditions = [AutomationExecutionTask.project_id == project_id]
        if status is not None:
            conditions.append(AutomationExecutionTask.status == status.value)
        total = int(
            await self.session.scalar(
                select(func.count(AutomationExecutionTask.id)).where(*conditions)
            )
            or 0
        )
        statement = (
            select(AutomationExecutionTask)
            .options(*self._load_options())
            .where(*conditions)
            .order_by(AutomationExecutionTask.created_at.desc(), AutomationExecutionTask.id.desc())
            .offset((current - 1) * size)
            .limit(size)
        )
        return list((await self.session.scalars(statement)).all()), total

    async def get_task(
        self,
        project_id: int,
        task_id: int,
        *,
        lock: bool = False,
    ) -> AutomationExecutionTask | None:
        """读取项目内任务；状态修改时可以锁定主记录。"""
        statement = (
            select(AutomationExecutionTask)
            .options(*self._load_options())
            .where(
                AutomationExecutionTask.id == task_id,
                AutomationExecutionTask.project_id == project_id,
            )
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_report(
        self,
        project_id: int,
        task_id: int,
    ) -> tuple[AutomationExecutionTask | None, list[AutomationExecutionStepResult]]:
        """读取任务汇总和按步骤号排序的脱敏报告。"""
        task = await self.get_task(project_id, task_id)
        if task is None:
            return None, []
        steps = list(
            (
                await self.session.scalars(
                    select(AutomationExecutionStepResult)
                    .where(AutomationExecutionStepResult.execution_task_id == task_id)
                    .order_by(AutomationExecutionStepResult.step_no)
                )
            ).all()
        )
        return task, steps

    async def get_submission_assets(
        self,
        project_id: int,
        definition_id: int,
        environment_id: int,
    ) -> tuple[AutomationDefinition | None, TestEnvironment | None]:
        """一次读取提交任务所需定义和环境，并限制二者属于同一项目。"""
        definition = await self.session.scalar(
            select(AutomationDefinition).where(
                AutomationDefinition.id == definition_id,
                AutomationDefinition.project_id == project_id,
                AutomationDefinition.deleted_at.is_(None),
            )
        )
        environment = await self.session.scalar(
            select(TestEnvironment).where(
                TestEnvironment.id == environment_id,
                TestEnvironment.project_id == project_id,
            )
        )
        return definition, environment

    async def claim_task(
        self,
        project_id: int,
        task_id: int,
        celery_task_id: str,
    ) -> AutomationExecutionTask | None:
        """以单条 UPDATE 原子领取仍为 PENDING 的任务，重复消息不会重复执行。"""
        claimed_id = await self.session.scalar(
            update(AutomationExecutionTask)
            .where(
                AutomationExecutionTask.id == task_id,
                AutomationExecutionTask.project_id == project_id,
                AutomationExecutionTask.status == AutomationExecutionStatus.PENDING.value,
            )
            .values(
                status=AutomationExecutionStatus.RUNNING.value,
                progress=10,
                current_stage="PREPARING_ENVIRONMENT",
                celery_task_id=celery_task_id,
                started_at=func.now(),
                error_message=None,
            )
            .returning(AutomationExecutionTask.id)
        )
        if claimed_id is None:
            await self.rollback()
            return None
        await self.commit()
        return await self.get_task(project_id, claimed_id)

    async def is_cancel_requested(self, task_id: int) -> bool:
        """轮询任务是否收到取消请求；只查询一个状态字段。"""
        status = await self.session.scalar(
            select(AutomationExecutionTask.status).where(AutomationExecutionTask.id == task_id)
        )
        return status == AutomationExecutionStatus.CANCEL_REQUESTED.value

    async def finish_task(
        self,
        task_id: int,
        status: AutomationExecutionStatus,
        *,
        result_summary: dict | None = None,
        error_message: str | None = None,
        step_results: list[dict] | None = None,
        commit: bool = True,
    ) -> bool:
        """只允许 RUNNING/CANCEL_REQUESTED 任务写入一次最终状态。

        ``commit=False`` 时只执行 ``flush``，让 Service 能继续在同一事务中写入
        自动化结果通知事件；默认值保持原有调用方的独立提交行为。
        """
        updated_id = await self.session.scalar(
            update(AutomationExecutionTask)
            .where(
                AutomationExecutionTask.id == task_id,
                AutomationExecutionTask.status.in_(
                    [
                        AutomationExecutionStatus.RUNNING.value,
                        AutomationExecutionStatus.CANCEL_REQUESTED.value,
                    ]
                ),
            )
            .values(
                status=status.value,
                progress=100,
                current_stage="FINISHED",
                result_summary=result_summary or {},
                error_message=error_message,
                finished_at=func.now(),
                updated_at=func.now(),
            )
            .returning(AutomationExecutionTask.id)
        )
        if updated_id is None:
            await self.rollback()
            return False
        for step in step_results or []:
            self.add(
                AutomationExecutionStepResult(
                    execution_task_id=task_id,
                    step_no=int(step["stepNo"]),
                    name=str(step["name"]),
                    status=str(step["status"]),
                    method=str(step["method"]),
                    path=str(step["path"]),
                    status_code=step.get("statusCode"),
                    duration_ms=step.get("durationMs"),
                    request_summary=dict(step.get("requestSummary") or {}),
                    response_summary=dict(step.get("responseSummary") or {}),
                    assertions=list(step.get("assertions") or []),
                    error_message=(str(step["errorMessage"])[:500] if step.get("errorMessage") else None),
                )
            )
        if commit:
            await self.commit()
        else:
            await self.flush()
        return True

    async def request_cancel(self, project_id: int, task_id: int) -> str | None:
        """待执行任务直接取消，运行中任务改为 CANCEL_REQUESTED 交给 Worker 终止。"""
        task = await self.get_task(project_id, task_id, lock=True)
        if task is None:
            return None
        if task.status == AutomationExecutionStatus.PENDING.value:
            task.status = AutomationExecutionStatus.CANCELLED.value
            task.progress = 100
            task.current_stage = "FINISHED"
            task.finished_at = utc_now()
        elif task.status == AutomationExecutionStatus.RUNNING.value:
            task.status = AutomationExecutionStatus.CANCEL_REQUESTED.value
            task.current_stage = "CANCELLING"
        else:
            return task.status
        await self.commit()
        return task.status

    async def finish_stale_tasks(
        self,
        *,
        now: datetime,
        grace_seconds: int,
        limit: int,
    ) -> tuple[int, int]:
        """收口因 Worker 异常退出而超过总超时的运行中任务。

        功能：锁定最早的 RUNNING/CANCEL_REQUESTED 任务，按每条任务自己的
        timeout_seconds 加统一宽限时间判断是否失联，并写入超时或取消终态。

        作用：正常 Worker 会主动终止 Pytest；本方法由周期补偿扫描调用，只处理
        Worker 已经无法继续更新状态的故障场景。

        为什么用它：Celery 开启延迟确认后会重投丢失任务，但消费者的原子领取
        会拒绝重复执行已经是 RUNNING 的记录；因此还需要数据库补偿把永久悬挂
        状态收口。使用行锁跳过并发扫描器，避免两个补偿实例重复修改同一任务。
        """
        statement = (
            select(AutomationExecutionTask)
            .where(
                AutomationExecutionTask.status.in_(
                    [
                        AutomationExecutionStatus.RUNNING.value,
                        AutomationExecutionStatus.CANCEL_REQUESTED.value,
                    ]
                ),
                AutomationExecutionTask.started_at.is_not(None),
            )
            .order_by(AutomationExecutionTask.started_at, AutomationExecutionTask.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        tasks = list((await self.session.scalars(statement)).all())
        timed_out = 0
        cancelled = 0
        for task in tasks:
            deadline = task.started_at + timedelta(seconds=task.timeout_seconds + grace_seconds)
            if deadline > now:
                continue
            if task.status == AutomationExecutionStatus.CANCEL_REQUESTED.value:
                task.status = AutomationExecutionStatus.CANCELLED.value
                task.error_message = "执行 Worker 失联，系统已收口取消状态"
                cancelled += 1
            else:
                task.status = AutomationExecutionStatus.TIMED_OUT.value
                task.error_message = "执行 Worker 失联且已超过任务总超时"
                timed_out += 1
            task.progress = 100
            task.current_stage = "FINISHED"
            task.finished_at = now

        if timed_out or cancelled:
            await self.commit()
        else:
            await self.rollback()
        return timed_out, cancelled
