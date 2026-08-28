"""通知渠道 Celery 入口；外部通知与自动化执行 Worker 相互隔离。"""

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionFactory
from app.repositories.automation_execution_tasks_repository import (
    AutomationExecutionTasksRepository,
)
from app.repositories.notification_channel_repository import (
    NotificationChannelRepository,
)
from app.services.notification_channel_service import NotificationChannelService
from app.workers.async_runtime import run_worker_coroutine


async def _send_automation_result(project_id: int, execution_task_id: int) -> bool:
    """创建独立数据库会话，读取任务终态并调用所有符合规则的通知渠道。"""
    async with AsyncSessionFactory() as session:
        service = NotificationChannelService(
            NotificationChannelRepository(session),
            automation_repository=AutomationExecutionTasksRepository(session),
        )
        result = await service.send_automation_result(project_id, execution_task_id)
        if result["failed"]:
            raise RuntimeError(
                f"{result['failed']} 个自动化结果通知渠道发送失败"
            )
        return True


@celery_app.task(
    name="notification.send_automation_result",
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def send_automation_result_task(
    project_id: int,
    execution_task_id: int,
) -> bool:
    """从 notifications 队列消费固定主键消息，不在 Redis 中保存渠道密钥。"""
    return run_worker_coroutine(
        _send_automation_result(project_id, execution_task_id)
    )
