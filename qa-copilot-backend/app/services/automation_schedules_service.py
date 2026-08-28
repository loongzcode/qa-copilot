"""定时回归计划管理与到期任务提交。"""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from app.core.constants import (
    AutomationDefinitionStatus,
    OutboxAggregateType,
    OutboxEventType,
    TestEnvironmentType,
)
from app.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models import AutomationExecutionTask, AutomationSchedule, User
from app.models.mixins import utc_now
from app.repositories.automation_schedules_repository import AutomationSchedulesRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.dto.automation_schedules import AutomationScheduleCreateDTO, AutomationScheduleUpdateDTO
from app.schemas.vo.automation_schedules import AutomationScheduleVO


class AutomationSchedulesService:
    """保存调度规则，并把到期计划转换为现有执行任务。"""

    def __init__(
        self,
        repository: AutomationSchedulesRepository,
        project_repository: TestProjectsRepository,
        outbox_repository: OutboxEventRepository,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.outbox_repository = outbox_repository

    async def _require_project(self, project_id: int, current_user: User) -> None:
        if await self.project_repository.get_accessible_project(project_id, current_user) is None:
            raise NotFoundException("项目不存在或无权访问")

    @staticmethod
    def _next_run(expression: str, timezone_name: str, base: datetime | None = None) -> datetime:
        """校验标准五段 Cron，并换算成带时区的下一次执行时间。"""
        if len(expression.split()) != 5 or not croniter.is_valid(expression):
            raise BadRequestException("Cron 必须是标准五段表达式，例如 0 2 * * *")
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise BadRequestException("未知时区") from exc
        local_base = (base or utc_now()).astimezone(timezone)
        return croniter(expression, local_base).get_next(datetime)

    @staticmethod
    def _vo(item: AutomationSchedule) -> AutomationScheduleVO:
        return AutomationScheduleVO(
            id=item.id,
            project_id=item.project_id,
            name=item.name,
            definition_id=item.definition_id,
            definition_name=item.definition.name,
            environment_id=item.environment_id,
            environment_name=item.environment.name,
            cron_expression=item.cron_expression,
            timezone=item.timezone,
            timeout_seconds=item.timeout_seconds,
            enabled=item.enabled,
            next_run_at=item.next_run_at,
            last_run_at=item.last_run_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _validate_assets(item: AutomationSchedule) -> None:
        if item.definition.status != AutomationDefinitionStatus.APPROVED.value:
            raise ConflictException("计划绑定的自动化定义不是已审批版本")
        if not item.environment.enabled:
            raise ConflictException("计划绑定的测试环境已停用")
        if item.environment.environment_type == TestEnvironmentType.PRODUCTION.value:
            raise BadRequestException("定时回归禁止使用生产环境")

    async def list_schedules(self, project_id: int, current_user: User) -> list[AutomationScheduleVO]:
        await self._require_project(project_id, current_user)
        return [self._vo(item) for item in await self.repository.list_schedules(project_id)]

    async def create(
        self, project_id: int, payload: AutomationScheduleCreateDTO, current_user: User
    ) -> AutomationScheduleVO:
        await self._require_project(project_id, current_user)
        item = AutomationSchedule(
            project_id=project_id,
            name=payload.name.strip(),
            definition_id=payload.definition_id,
            environment_id=payload.environment_id,
            cron_expression=payload.cron_expression.strip(),
            timezone=payload.timezone,
            timeout_seconds=payload.timeout_seconds,
            enabled=payload.enabled,
            next_run_at=self._next_run(payload.cron_expression, payload.timezone),
            created_by=current_user.id,
        )
        self.repository.add(item)
        await self.repository.flush()
        loaded = await self.repository.get_schedule(project_id, item.id)
        if loaded is None:
            raise RuntimeError("计划创建后无法读取")
        self._validate_assets(loaded)
        await self.repository.commit()
        return self._vo(loaded)

    async def update(
        self,
        project_id: int,
        schedule_id: int,
        payload: AutomationScheduleUpdateDTO,
        current_user: User,
    ) -> AutomationScheduleVO:
        await self._require_project(project_id, current_user)
        item = await self.repository.get_schedule(project_id, schedule_id, lock=True)
        if item is None:
            raise NotFoundException("定时回归计划不存在")
        item.name = payload.name.strip()
        item.definition_id = payload.definition_id
        item.environment_id = payload.environment_id
        item.cron_expression = payload.cron_expression.strip()
        item.timezone = payload.timezone
        item.timeout_seconds = payload.timeout_seconds
        item.enabled = payload.enabled
        item.next_run_at = self._next_run(payload.cron_expression, payload.timezone)
        await self.repository.flush()
        # 外键 ID 已变化时清除旧关系缓存，确保下面校验的是新定义和新环境。
        self.repository.session.expire(item, ["definition", "environment"])
        loaded = await self.repository.get_schedule(project_id, schedule_id)
        if loaded is None:
            raise RuntimeError("计划更新后无法读取")
        self._validate_assets(loaded)
        await self.repository.commit()
        return self._vo(loaded)

    async def delete(self, project_id: int, schedule_id: int, current_user: User) -> None:
        await self._require_project(project_id, current_user)
        item = await self.repository.get_schedule(project_id, schedule_id, lock=True)
        if item is None:
            raise NotFoundException("定时回归计划不存在")
        await self.repository.delete(item)
        await self.repository.commit()

    async def dispatch_due(self, now: datetime | None = None) -> dict[str, int]:
        """扫描到期计划，在同一事务中创建执行任务与发件箱事件。"""
        scan_time = now or utc_now()
        created = skipped = 0
        for schedule in await self.repository.list_due(scan_time):
            schedule.last_run_at = scan_time
            schedule.next_run_at = self._next_run(schedule.cron_expression, schedule.timezone, scan_time)
            try:
                self._validate_assets(schedule)
            except BadRequestException, ConflictException:
                schedule.enabled = False
                skipped += 1
                continue
            if await self.repository.has_active_execution(schedule.definition_id):
                skipped += 1
                continue
            task = AutomationExecutionTask(
                project_id=schedule.project_id,
                definition_id=schedule.definition_id,
                environment_id=schedule.environment_id,
                timeout_seconds=schedule.timeout_seconds,
                definition_hash=schedule.definition.definition_hash,
                environment_updated_at=schedule.environment.updated_at,
                requested_by=schedule.created_by,
                result_summary={"scheduleId": schedule.id, "scheduleName": schedule.name},
            )
            self.repository.add(task)
            await self.repository.flush()
            self.outbox_repository.add_pending_event(
                event_type=OutboxEventType.AUTOMATION_EXECUTION.value,
                aggregate_type=OutboxAggregateType.AUTOMATION_EXECUTION.value,
                aggregate_id=task.id,
                payload={"project_id": schedule.project_id, "execution_task_id": task.id},
            )
            created += 1
        await self.repository.commit()
        return {"created": created, "skipped": skipped}
