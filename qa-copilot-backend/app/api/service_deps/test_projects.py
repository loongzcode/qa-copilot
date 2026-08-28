from typing import Annotated

from app.core.deps import DbSession
from app.repositories.test_project_members_repository import TestProjectMembersRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.repositories.user_repository import UserRepository
from app.services.test_projects_service import TestProjectsService
from fastapi import Depends


def get_test_projects_service(db: DbSession) -> TestProjectsService:

    return TestProjectsService(
        TestProjectsRepository(session=db), UserRepository(session=db), TestProjectMembersRepository(session=db)
    )


TestProjectsServiceDep = Annotated[TestProjectsService, Depends(get_test_projects_service)]
