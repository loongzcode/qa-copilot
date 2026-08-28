"""组装需求拆解 API 使用的请求级依赖。"""

from typing import Annotated

from app.core.deps import DbSession
from app.repositories.requirement_extraction_tasks_repository import (
    RequirementExtractionTasksRepository,
)
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.requirement_extraction_service import RequirementExtractionService
from fastapi import Depends


def get_requirement_extraction_service(db: DbSession) -> RequirementExtractionService:
    """让本次 HTTP 请求中的多个 Repository 共用同一个事务 Session。"""

    return RequirementExtractionService(
        requirement_extraction_tasks_repository=RequirementExtractionTasksRepository(
            session=db
        ),
        requirements_repository=RequirementsRepository(session=db),
        test_project_repository=TestProjectsRepository(session=db),
    )


RequirementExtractionServiceDep = Annotated[
    RequirementExtractionService,
    Depends(get_requirement_extraction_service),
]
