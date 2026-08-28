from typing import Annotated

from app.core.deps import DbSession
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.test_cases_repository import TestCasesRepository
from app.repositories.test_modules_repository import TestModulesRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.case_coverage_service import CaseCoverageService
from app.services.test_cases_service import TestCasesService
from fastapi import Depends


def get_test_cases_service(db: DbSession) -> TestCasesService:
    """使用当前请求的数据库会话组装用例模块依赖。"""

    repository = TestCasesRepository(session=db)
    coverage_service = CaseCoverageService(
        repository=repository,
        ai_model_repository=AIModelRepository(session=db),
        prompt_template_repository=PromptTemplateRepository(session=db),
    )
    return TestCasesService(
        repository=repository,
        project_repository=TestProjectsRepository(session=db),
        module_repository=TestModulesRepository(session=db),
        requirement_repository=RequirementsRepository(session=db),
        coverage_service=coverage_service,
    )


TestCasesServiceDep = Annotated[
    TestCasesService,
    Depends(get_test_cases_service),
]
