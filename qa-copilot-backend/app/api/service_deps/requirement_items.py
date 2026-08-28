"""原子需求点 Service 的请求级依赖组装。"""

from typing import Annotated

from app.core.deps import DbSession
from app.repositories.requirement_items_repository import RequirementItemsRepository
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.requirement_items_service import RequirementItemsService
from fastapi import Depends


def get_requirement_items_service(db: DbSession) -> RequirementItemsService:
    """让需求点相关 Repository 共用同一个请求级事务 Session。"""

    return RequirementItemsService(
        repository=RequirementItemsRepository(session=db),
        requirements_repository=RequirementsRepository(session=db),
        test_project_repository=TestProjectsRepository(session=db),
    )


RequirementItemsServiceDep = Annotated[
    RequirementItemsService,
    Depends(get_requirement_items_service),
]
