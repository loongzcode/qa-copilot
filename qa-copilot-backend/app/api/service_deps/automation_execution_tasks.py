from typing import Annotated

from app.core.deps import DbSession
from app.repositories.automation_execution_tasks_repository import AutomationExecutionTasksRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.test_environments_api_repository import TestEnvironmentsApiRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.automation_execution_service import AutomationExecutionService
from app.services.test_environments_api_service import TestEnvironmentsApiService
from fastapi import Depends


def get_automation_execution_service(db: DbSession) -> AutomationExecutionService:
    """使用同一请求级事务组装任务与发件箱 Repository。"""
    project_repository = TestProjectsRepository(db)
    environment_repository = TestEnvironmentsApiRepository(db)
    return AutomationExecutionService(
        repository=AutomationExecutionTasksRepository(db),
        project_repository=project_repository,
        outbox_repository=OutboxEventRepository(db),
        environment_service=TestEnvironmentsApiService(
            repository=environment_repository,
            project_repository=project_repository,
        ),
    )


AutomationExecutionServiceDep = Annotated[
    AutomationExecutionService,
    Depends(get_automation_execution_service),
]
