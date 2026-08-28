"""Supervisor 顺序执行任务的 Celery 入口和依赖组装。"""

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionFactory
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.repositories.quality_delivery_repository import QualityDeliveryRepository
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.supervisor_repository import SupervisorRepository
from app.repositories.test_cases_repository import TestCasesRepository
from app.repositories.test_modules_repository import TestModulesRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.case_coverage_service import CaseCoverageService
from app.services.quality_delivery_service import QualityDeliveryService
from app.services.supervisor_capability_executor import SupervisorCapabilityExecutor
from app.services.supervisor_execution_service import SupervisorExecutionService
from app.services.test_cases_service import TestCasesService
from app.workers.async_runtime import run_worker_coroutine


async def _run_supervisor_execution(project_id: int, run_id: int) -> bool:
    """在 Worker 自己的数据库会话中组装并运行 Supervisor 执行服务。"""
    async with AsyncSessionFactory() as session:
        project_repository = TestProjectsRepository(session)
        quality_delivery_service = QualityDeliveryService(
            QualityDeliveryRepository(session),
            project_repository,
            RequirementsRepository(session),
        )
        test_cases_repository = TestCasesRepository(session)
        test_cases_service = TestCasesService(
            repository=test_cases_repository,
            project_repository=project_repository,
            module_repository=TestModulesRepository(session),
            requirement_repository=RequirementsRepository(session),
            coverage_service=CaseCoverageService(
                repository=test_cases_repository,
                ai_model_repository=AIModelRepository(session),
                prompt_template_repository=PromptTemplateRepository(session),
            ),
        )
        capability_executor = SupervisorCapabilityExecutor(
            quality_delivery_service,
            test_cases_service,
        )
        service = SupervisorExecutionService(
            repository=SupervisorRepository(session),
            auth_repository=AuthRepository(session),
            capability_executor=capability_executor,
        )
        return await service.execute(project_id, run_id)


@celery_app.task(name="supervisor.execute_run")
def execute_supervisor_run_task(project_id: int, run_id: int) -> bool:
    """消费只包含主键的可信消息，计划正文和权限始终从 PostgreSQL 重新读取。"""
    return run_worker_coroutine(_run_supervisor_execution(project_id, run_id))
