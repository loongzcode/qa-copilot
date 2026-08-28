"""定时回归计划请求级依赖。"""

from typing import Annotated

from app.core.deps import DbSession
from app.repositories.automation_schedules_repository import AutomationSchedulesRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.automation_schedules_service import AutomationSchedulesService
from fastapi import Depends


def get_automation_schedules_service(db: DbSession) -> AutomationSchedulesService:
    return AutomationSchedulesService(
        AutomationSchedulesRepository(db),
        TestProjectsRepository(db),
        OutboxEventRepository(db),
    )


AutomationSchedulesServiceDep = Annotated[AutomationSchedulesService, Depends(get_automation_schedules_service)]
