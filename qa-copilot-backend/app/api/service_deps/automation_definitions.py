from typing import Annotated

from app.core.deps import DbSession
from app.repositories.automation_definitions_repository import (
    AutomationDefinitionsRepository,
)
from app.repositories.test_cases_repository import TestCasesRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.automation_definitions_service import AutomationDefinitionsService
from fastapi import Depends


def get_automation_definitions_service(db: DbSession) -> AutomationDefinitionsService:
    """使用同一个请求级数据库会话组装自动化定义业务依赖。"""
    return AutomationDefinitionsService(
        repository=AutomationDefinitionsRepository(session=db),
        project_repository=TestProjectsRepository(session=db),
        test_case_repository=TestCasesRepository(session=db),
    )


AutomationDefinitionsServiceDep = Annotated[
    AutomationDefinitionsService,
    Depends(get_automation_definitions_service),
]
