from typing import Annotated

from app.core.deps import DbSession
from app.repositories.test_environments_api_repository import TestEnvironmentsApiRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.test_environments_api_service import TestEnvironmentsApiService
from fastapi import Depends


def get_test_environments_api_service(db: DbSession) -> TestEnvironmentsApiService:

    return TestEnvironmentsApiService(
        TestEnvironmentsApiRepository(session=db),TestProjectsRepository(session=db),
    )


TestEnvironmentsApiServiceDep = Annotated[TestEnvironmentsApiService, Depends(get_test_environments_api_service)]
