"""测试用例生成任务的 Celery 入口与异步依赖组装。"""

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionFactory
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.test_cases_repository import TestCasesRepository
from app.services.case_coverage_service import CaseCoverageService
from app.services.case_generation_execution_service import CaseGenerationExecutionService
from app.workers.async_runtime import run_worker_coroutine


async def _run_case_generation(project_id: int, generation_task_id: int) -> bool:
    """在独立数据库 Session 中组装并执行生成服务。

    功能：让 Repository、覆盖服务和执行服务共用同一个 AsyncSession。
    作用：隔离 Celery 同步入口与异步业务代码，任务结束时自动归还数据库连接。
    为什么用它：后台 Worker 没有 FastAPI 请求依赖，必须显式组装；async with 即使
    发生异常也能关闭 Session，避免长时间运行后连接泄漏。
    """
    async with AsyncSessionFactory() as session:
        test_cases_repository = TestCasesRepository(session)
        ai_model_repository = AIModelRepository(session)
        prompt_template_repository = PromptTemplateRepository(session)
        coverage_service = CaseCoverageService(
            repository=test_cases_repository,
            ai_model_repository=ai_model_repository,
            prompt_template_repository=prompt_template_repository,
        )
        service = CaseGenerationExecutionService(
            repository=test_cases_repository,
            requirements_repository=RequirementsRepository(session),
            ai_model_repository=ai_model_repository,
            prompt_template_repository=prompt_template_repository,
            coverage_service=coverage_service,
        )
        return await service.execute(project_id, generation_task_id)


@celery_app.task(bind=True, name="case.generate_missing")
def generate_missing_cases_task(
    self: object,
    project_id: int,
    generation_task_id: int,
) -> bool:
    """消费一条缺失用例生成消息并桥接到异步主流程。

    功能：接收 Dispatcher 投递的项目和数据库任务 ID。
    作用：注册为 ``case.generate_missing``，由 case-generation 队列专门消费。
    为什么用它：消息只携带不可变主键，正文和权限快照仍从数据库读取，避免大消息、
    敏感需求正文进入 Redis；数据库任务状态负责幂等而非依赖 Celery 恰好一次。
    """
    del self
    return run_worker_coroutine(
        _run_case_generation(project_id, generation_task_id)
    )
