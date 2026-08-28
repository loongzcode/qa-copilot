"""定时回归计划查询和到期认领。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.constants import AutomationExecutionStatus
from app.models import AutomationExecutionTask, AutomationSchedule
from app.repositories.base_repository import BaseRepository


class AutomationSchedulesRepository(BaseRepository):
    async def list_schedules(self, project_id: int) -> list[AutomationSchedule]:
        return list(
            (
                await self.session.scalars(
                    select(AutomationSchedule)
                    .options(
                        selectinload(AutomationSchedule.definition),
                        selectinload(AutomationSchedule.environment),
                    )
                    .where(AutomationSchedule.project_id == project_id)
                    .order_by(AutomationSchedule.id.desc())
                )
            ).all()
        )

    async def get_schedule(self, project_id: int, schedule_id: int, *, lock: bool = False) -> AutomationSchedule | None:
        statement = (
            select(AutomationSchedule)
            .options(
                selectinload(AutomationSchedule.definition),
                selectinload(AutomationSchedule.environment),
            )
            .where(
                AutomationSchedule.project_id == project_id,
                AutomationSchedule.id == schedule_id,
            )
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_due(self, now: datetime, limit: int = 100) -> list[AutomationSchedule]:
        """锁定一批到期计划；skip_locked 允许多个调度器安全并行。"""
        return list(
            (
                await self.session.scalars(
                    select(AutomationSchedule)
                    .options(
                        selectinload(AutomationSchedule.definition),
                        selectinload(AutomationSchedule.environment),
                    )
                    .where(
                        AutomationSchedule.enabled.is_(True),
                        AutomationSchedule.next_run_at <= now,
                    )
                    .order_by(AutomationSchedule.next_run_at, AutomationSchedule.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )

    async def has_active_execution(self, definition_id: int) -> bool:
        return (
            await self.session.scalar(
                select(AutomationExecutionTask.id)
                .where(
                    AutomationExecutionTask.definition_id == definition_id,
                    AutomationExecutionTask.status.in_(
                        [
                            AutomationExecutionStatus.PENDING.value,
                            AutomationExecutionStatus.RUNNING.value,
                            AutomationExecutionStatus.CANCEL_REQUESTED.value,
                        ]
                    ),
                )
                .limit(1)
            )
            is not None
        )
