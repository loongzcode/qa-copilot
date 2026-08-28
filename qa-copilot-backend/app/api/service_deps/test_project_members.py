from typing import Annotated

from app.core.deps import DbSession
from app.repositories.test_project_members_repository import (
    TestProjectMembersRepository,
)
from app.repositories.test_projects_repository import TestProjectsRepository
from app.repositories.user_repository import UserRepository
from app.services.test_project_members_service import TestProjectMembersService
from fastapi import Depends


def get_test_project_members_service(db: DbSession) -> TestProjectMembersService:

    return TestProjectMembersService(
        TestProjectMembersRepository(session=db), TestProjectsRepository(session=db), UserRepository(session=db)
    )


TestProjectMembersServiceDep = Annotated[TestProjectMembersService, Depends(get_test_project_members_service)]
