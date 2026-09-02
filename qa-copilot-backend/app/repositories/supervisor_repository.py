"""Supervisor 运行和计划步骤的数据访问层。"""

from collections.abc import Collection
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.agents.supervisor_state_machine import can_transition_supervisor_run, can_transition_supervisor_step
from app.core.constants import SupervisorExecutionStepStatus, SupervisorRunStatus
from app.models import SupervisorPlanStep, SupervisorRun, SupervisorSession
from app.repositories.base_repository import BaseRepository


class SupervisorRepository(BaseRepository):
    """封装 Supervisor 计划保存、项目隔离查询和原子状态更新。"""

    def add_run(self, run: SupervisorRun) -> None:
        """把运行及其步骤加入当前事务；是否提交由 Service 统一决定。"""
        self.add(run)

    def add_session(self, session: SupervisorSession) -> None:
        """把聊天会话加入当前事务，提交时机由 Service 控制。"""
        self.add(session)

    async def get_session(
        self, project_id: int, session_id: int, created_by: int | None = None
    ) -> SupervisorSession | None:
        """按项目和创建人读取未删除会话，避免用户看到别人的私人聊天。"""
        conditions = [
            SupervisorSession.id == session_id,
            SupervisorSession.project_id == project_id,
            SupervisorSession.deleted_at.is_(None),
        ]
        if created_by is not None:
            conditions.append(SupervisorSession.created_by == created_by)
        return await self.session.scalar(select(SupervisorSession).where(*conditions))

    async def list_sessions(self, project_id: int, created_by: int) -> list[SupervisorSession]:
        """按最近使用时间返回当前用户在项目中的聊天会话。"""
        return list(
            (
                await self.session.scalars(
                    select(SupervisorSession)
                    .where(
                        SupervisorSession.project_id == project_id,
                        SupervisorSession.created_by == created_by,
                        SupervisorSession.deleted_at.is_(None),
                    )
                    .order_by(SupervisorSession.updated_at.desc(), SupervisorSession.id.desc())
                )
            ).all()
        )

    async def get_run(self, project_id: int, run_id: int, *, lock: bool = False) -> SupervisorRun | None:
        """读取一个项目内的 Supervisor 运行及全部步骤。

        功能：同时按 project_id 和 run_id 查询，按需锁定主记录。
        作用：详情页面、恢复执行和取消操作共用该入口，避免跨项目读取。
        为什么用它：project_id 必须进入 SQL 条件，不能只依赖前端传值；selectinload 用第二条查询批量加载步骤，
        避免逐步触发 N+1 查询。修改状态时使用行锁可阻止两个请求同时改同一运行。
        """
        statement = (
            select(SupervisorRun)
            .options(selectinload(SupervisorRun.steps))
            # 同一个请求中可能刚通过 UPDATE 推进了状态或新增步骤。
            # expire_on_commit=False 会保留身份映射中的旧对象，因此这里强制
            # 用数据库最新值覆盖，确保创建/取消接口立即返回真实步骤状态。
            .execution_options(populate_existing=True)
            .where(SupervisorRun.id == run_id, SupervisorRun.project_id == project_id)
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_runs(
        self,
        project_id: int,
        current: int,
        size: int,
        status: SupervisorRunStatus | None = None,
        session_id: int | None = None,
    ) -> tuple[list[SupervisorRun], int]:
        """分页查询项目内 Supervisor 运行，列表阶段不加载步骤详情。"""
        conditions = [SupervisorRun.project_id == project_id]
        if status is not None:
            conditions.append(SupervisorRun.status == status.value)
        if session_id is not None:
            conditions.append(SupervisorRun.session_id == session_id)
        total = int(await self.session.scalar(select(func.count(SupervisorRun.id)).where(*conditions)) or 0)
        statement = (
            select(SupervisorRun)
            .where(*conditions)
            .order_by(SupervisorRun.created_at.desc(), SupervisorRun.id.desc())
            .offset((current - 1) * size)
            .limit(size)
        )
        return list((await self.session.scalars(statement)).all()), total

    async def transition_run(
        self,
        project_id: int,
        run_id: int,
        expected_statuses: Collection[SupervisorRunStatus],
        target_status: SupervisorRunStatus,
        *,
        current_step_no: int | None = None,
        result_summary: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> bool:
        """只在数据库状态仍符合预期时原子推进 Supervisor 运行。

        功能：以一条带当前状态条件的 UPDATE 修改主任务，并返回是否抢占成功。
        作用：防止两个 Worker、重复消息或用户取消与执行完成同时覆盖彼此结果。
        为什么用它：先查询再修改存在竞态窗口；条件更新加 RETURNING 由 PostgreSQL 一次完成比较和写入。
        """
        if not expected_statuses:
            raise ValueError("Supervisor 运行状态更新必须提供预期状态")
        illegal_sources = [
            status.value for status in expected_statuses if not can_transition_supervisor_run(status, target_status)
        ]
        if illegal_sources:
            raise ValueError(f"Supervisor 运行存在非法状态流转：{illegal_sources} -> {target_status.value}")
        values: dict[str, Any] = {
            "status": target_status.value,
            "error_message": error_message,
            "updated_at": func.now(),
        }
        if current_step_no is not None:
            values["current_step_no"] = current_step_no
        if result_summary is not None:
            values["result_summary"] = result_summary
        if target_status == SupervisorRunStatus.RUNNING:
            values["started_at"] = func.now()
            values["execution_heartbeat_at"] = func.now()
        if target_status in {
            SupervisorRunStatus.PLAN_REJECTED,
            SupervisorRunStatus.SUCCEEDED,
            SupervisorRunStatus.FAILED,
            SupervisorRunStatus.CANCELLED,
        }:
            values["finished_at"] = func.now()

        updated_id = await self.session.scalar(
            update(SupervisorRun)
            .where(
                SupervisorRun.id == run_id,
                SupervisorRun.project_id == project_id,
                SupervisorRun.status.in_([status.value for status in expected_statuses]),
            )
            .values(**values)
            .returning(SupervisorRun.id)
        )
        return updated_id is not None

    async def transition_step(
        self,
        run_id: int,
        step_id: int,
        expected_statuses: Collection[SupervisorExecutionStepStatus],
        target_status: SupervisorExecutionStepStatus,
        *,
        tool_task_id: int | None = None,
        result_snapshot: dict[str, Any] | None = None,
        error_message: str | None = None,
        approval_decided_by: int | None = None,
        approval_decision: str | None = None,
        approval_comment: str | None = None,
    ) -> bool:
        """以运行 ID 限定并原子推进一个计划步骤，避免跨运行误改。"""
        if not expected_statuses:
            raise ValueError("Supervisor 步骤状态更新必须提供预期状态")
        illegal_sources = [
            status.value for status in expected_statuses if not can_transition_supervisor_step(status, target_status)
        ]
        if illegal_sources:
            raise ValueError(f"Supervisor 步骤存在非法状态流转：{illegal_sources} -> {target_status.value}")
        values: dict[str, Any] = {
            "status": target_status.value,
            "error_message": error_message,
            "updated_at": func.now(),
        }
        if tool_task_id is not None:
            values["tool_task_id"] = tool_task_id
        if result_snapshot is not None:
            values["result_snapshot"] = result_snapshot
        if approval_decided_by is not None:
            values["approval_decided_by"] = approval_decided_by
            values["approval_decision"] = approval_decision
            values["approval_comment"] = approval_comment
            values["approval_decided_at"] = func.now()
        if target_status == SupervisorExecutionStepStatus.RUNNING:
            values["started_at"] = func.now()
        if target_status in {
            SupervisorExecutionStepStatus.REJECTED,
            SupervisorExecutionStepStatus.SUCCEEDED,
            SupervisorExecutionStepStatus.FAILED,
            SupervisorExecutionStepStatus.SKIPPED,
            SupervisorExecutionStepStatus.CANCELLED,
        }:
            values["finished_at"] = func.now()

        updated_id = await self.session.scalar(
            update(SupervisorPlanStep)
            .where(
                SupervisorPlanStep.id == step_id,
                SupervisorPlanStep.run_id == run_id,
                SupervisorPlanStep.status.in_([status.value for status in expected_statuses]),
            )
            .values(**values)
            .returning(SupervisorPlanStep.id)
        )
        return updated_id is not None

    async def update_running_progress(self, project_id: int, run_id: int, current_step_no: int) -> bool:
        """只更新运行中任务的当前步骤编号，不重复触发状态流转。

        功能：在每个步骤开始时记录页面应展示的当前位置。
        作用：与 ``transition_run`` 分开，因为主运行已经是 RUNNING，步骤推进不是一次新的状态变化。
        为什么用它：禁止 RUNNING→RUNNING 的伪状态流转，让状态机继续只描述真正的状态变化。
        """
        updated_id = await self.session.scalar(
            update(SupervisorRun)
            .where(
                SupervisorRun.id == run_id,
                SupervisorRun.project_id == project_id,
                SupervisorRun.status == SupervisorRunStatus.RUNNING.value,
            )
            .values(
                current_step_no=current_step_no,
                execution_heartbeat_at=func.now(),
                updated_at=func.now(),
            )
            .returning(SupervisorRun.id)
        )
        return updated_id is not None

    async def lock_stale_running_runs(
        self,
        *,
        stale_before: datetime,
        limit: int,
    ) -> list[SupervisorRun]:
        """锁定长时间没有心跳的运行，供周期补偿安全地重新投递。"""
        statement = (
            select(SupervisorRun)
            .options(selectinload(SupervisorRun.steps))
            .where(
                SupervisorRun.status == SupervisorRunStatus.RUNNING.value,
                func.coalesce(
                    SupervisorRun.execution_heartbeat_at,
                    SupervisorRun.started_at,
                    SupervisorRun.updated_at,
                )
                < stale_before,
            )
            .order_by(SupervisorRun.updated_at, SupervisorRun.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self.session.scalars(statement)).all())

    async def mark_running_requeued(self, project_id: int, run_id: int) -> bool:
        """增加恢复次数并刷新心跳，形成下一次超时判断的新起点。"""
        updated_id = await self.session.scalar(
            update(SupervisorRun)
            .where(
                SupervisorRun.id == run_id,
                SupervisorRun.project_id == project_id,
                SupervisorRun.status == SupervisorRunStatus.RUNNING.value,
            )
            .values(
                execution_recovery_count=SupervisorRun.execution_recovery_count + 1,
                execution_heartbeat_at=func.now(),
                updated_at=func.now(),
            )
            .returning(SupervisorRun.id)
        )
        return updated_id is not None
