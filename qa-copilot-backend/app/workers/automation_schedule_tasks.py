"""Celery Beat 触发的定时回归扫描任务。"""

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionFactory
from app.repositories.automation_schedules_repository import AutomationSchedulesRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.automation_schedules_service import AutomationSchedulesService
from app.workers.async_runtime import run_worker_coroutine


async def _dispatch_due_schedules() -> dict[str, int]:
    async with AsyncSessionFactory() as session:
        return await AutomationSchedulesService(
            AutomationSchedulesRepository(session),
            TestProjectsRepository(session),
            OutboxEventRepository(session),
        ).dispatch_due()


@celery_app.task(name="automation.dispatch_schedules")
def dispatch_automation_schedules_task() -> dict[str, int]:
    """每分钟扫描到期计划；实际执行仍由 automation-execution 队列消费。"""
    return run_worker_coroutine(_dispatch_due_schedules())
