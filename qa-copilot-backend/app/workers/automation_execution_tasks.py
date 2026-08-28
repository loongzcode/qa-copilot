"""自动化执行任务的 Celery 同步入口和异步依赖组装。"""

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionFactory
from app.repositories.automation_execution_tasks_repository import AutomationExecutionTasksRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.test_environments_api_repository import TestEnvironmentsApiRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.automation_execution_service import AutomationExecutionService
from app.services.test_environments_api_service import TestEnvironmentsApiService
from app.workers.async_runtime import run_worker_coroutine


async def _run_automation_execution(
    project_id: int,
    execution_task_id: int,
    celery_task_id: str,
) -> bool:
    """在独立数据库会话中组装执行服务并运行一条任务。"""
    async with AsyncSessionFactory() as session:
        project_repository = TestProjectsRepository(session)
        environment_repository = TestEnvironmentsApiRepository(session)
        environment_service = TestEnvironmentsApiService(
            repository=environment_repository,
            project_repository=project_repository,
        )
        service = AutomationExecutionService(
            repository=AutomationExecutionTasksRepository(session),
            project_repository=project_repository,
            outbox_repository=OutboxEventRepository(session),
            environment_service=environment_service,
        )
        return await service.execute(project_id, execution_task_id, celery_task_id)


@celery_app.task(bind=True, name="automation.execute")
def execute_automation_task(self: object, project_id: int, execution_task_id: int) -> bool:
    """消费固定主键消息；任务正文和密钥始终从 PostgreSQL 读取。"""
    celery_task_id = str(getattr(getattr(self, "request", None), "id", "") or "")
    return run_worker_coroutine(
        _run_automation_execution(project_id, execution_task_id, celery_task_id)
    )
