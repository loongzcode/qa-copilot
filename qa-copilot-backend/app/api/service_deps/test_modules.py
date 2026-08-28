from typing import Annotated

from app.core.deps import DbSession
from app.repositories.test_modules_repository import TestModulesRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.test_modules_service import TestModulesService
from fastapi import Depends


def get_test_modules_service(db: DbSession) -> TestModulesService:

    return TestModulesService(TestModulesRepository(session=db), project_repository=TestProjectsRepository(session=db))


TestModulesServiceDep = Annotated[TestModulesService, Depends(get_test_modules_service)]
