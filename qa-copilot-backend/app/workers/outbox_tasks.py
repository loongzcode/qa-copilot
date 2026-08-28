"""定时发布 PostgreSQL 事务性发件箱事件的 Celery 任务入口。"""

import logging
import os
import socket
from dataclasses import asdict

from redis.asyncio import Redis

from app.core.celery_app import CELERY_QUEUE_NAMES, celery_app
from app.core.config import settings
from app.core.constants import OutboxEventStatus, OutboxEventType
from app.core.database import AsyncSessionFactory
from app.core.metrics import (
    set_celery_broker_queue_depth,
    set_outbox_queue_depth,
)
from app.repositories.automation_execution_tasks_repository import AutomationExecutionTasksRepository
from app.repositories.background_recovery_repository import BackgroundRecoveryRepository
from app.repositories.knowledge_document_repository import KnowledgeDocumentRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.supervisor_repository import SupervisorRepository
from app.services.background_task_recovery_service import (
    BackgroundTaskRecoveryService,
)
from app.services.outbox_event_service import OutboxEventService
from app.workers.async_runtime import (
    register_worker_cleanup,
    run_worker_coroutine,
)

_queue_metrics_redis: Redis | None = None
logger = logging.getLogger(__name__)


async def _run_publish_batch(publisher_id: str) -> dict[str, int]:
    """创建独立数据库 Session 并执行一轮发件箱发布。

    功能：组装 Repository 和 Service，发布到期事件并返回本轮统计。

    作用：隔离 Celery 同步入口与异步数据库业务，任务结束后自动关闭 Session。

    为什么用它：后台任务没有 FastAPI 请求级依赖注入，必须显式创建 Session；
    ``async with`` 可以在成功和异常分支中可靠归还连接。
    """

    async with AsyncSessionFactory() as session:
        repository = OutboxEventRepository(session)
        service = OutboxEventService(
            repository=repository,
        )
        result = await service.publish_batch(publisher_id=publisher_id)
        try:
            queue_depth_rows = await repository.count_active_events_by_type_and_status()
            set_outbox_queue_depth(
                queue_depth_rows,
                event_types=(item.value for item in OutboxEventType),
                statuses=(
                    OutboxEventStatus.PENDING.value,
                    OutboxEventStatus.PROCESSING.value,
                    OutboxEventStatus.RETRY.value,
                ),
            )
            await _refresh_celery_broker_queue_depth()
        except Exception:
            # 监控刷新失败不能把已经成功完成的消息发布批次改判为失败。
            # 下一轮周期任务还会再次从 PostgreSQL 聚合并修正 Gauge。
            logger.exception("刷新发件箱积压指标失败")
        return asdict(result)


async def _refresh_celery_broker_queue_depth() -> None:
    """从 Redis 批量读取所有已配置 Celery 队列的等待任务数量。

    功能：通过一个非事务 Pipeline 依次添加 ``LLEN``，再用一次网络往返执行。

    作用：由每轮发件箱发布任务调用，刷新真正进入 Broker、尚未被 Worker 领取的
    任务数量。

    为什么用它：逐个执行会产生多次 Redis 网络往返；Pipeline 能保持相同读取
    语义并减少监控开销。Redis 客户端在 Worker 进程内复用，退出时统一关闭。
    """

    global _queue_metrics_redis
    if not settings.metrics_enabled:
        return
    if _queue_metrics_redis is None:
        _queue_metrics_redis = Redis.from_url(settings.redis_url)
    pipeline = _queue_metrics_redis.pipeline(transaction=False)
    for queue_name in CELERY_QUEUE_NAMES:
        pipeline.llen(queue_name)
    counts = await pipeline.execute()
    set_celery_broker_queue_depth(
        [
            (queue_name, int(count))
            for queue_name, count in zip(
                CELERY_QUEUE_NAMES,
                counts,
                strict=True,
            )
        ],
        queue_names=CELERY_QUEUE_NAMES,
    )


async def _run_background_recovery() -> dict[str, int]:
    """创建独立 Session 并执行一轮超时任务补偿扫描。"""

    async with AsyncSessionFactory() as session:
        service = BackgroundTaskRecoveryService(
            knowledge_document_repository=KnowledgeDocumentRepository(session),
            outbox_event_repository=OutboxEventRepository(session),
            automation_execution_repository=AutomationExecutionTasksRepository(session),
            background_recovery_repository=BackgroundRecoveryRepository(session),
            supervisor_repository=SupervisorRepository(session),
        )
        return asdict(await service.recover())


@celery_app.task(name="system.publish_outbox")
def publish_outbox_events_task() -> dict[str, int]:
    """由 Celery Beat 周期触发一轮发件箱发布。

    功能：生成当前发布器实例标识，并在复用事件循环中运行异步发布批次。

    作用：它是 ``system.publish_outbox`` 的 Celery 注册入口，由专用
    ``system-outbox`` Worker 消费。

    为什么用它：将轮询作为短周期后台任务交给 Celery Beat，部署时无需再维护
    自定义常驻 ``while`` 循环；即使某轮失败，下一调度周期仍会继续恢复。
    """

    publisher_id = f"{socket.gethostname()}:{os.getpid()}"
    return run_worker_coroutine(_run_publish_batch(publisher_id))


@celery_app.task(name="system.recover_background_tasks")
def recover_background_tasks_task() -> dict[str, int]:
    """周期扫描并恢复超时的发件箱事件和知识文档索引任务。

    功能：运行数据库补偿扫描并返回恢复数量。

    作用：与发件箱发布任务共用 ``system-outbox`` 专用 Worker，由 Celery Beat
    按较低频率触发。

    为什么用它：补偿属于控制面短任务，与模型计算队列隔离可避免被长任务
    阻塞；每轮有批量上限，下一周期会继续处理剩余数据。
    """

    return run_worker_coroutine(_run_background_recovery())


async def _close_queue_metrics_redis() -> None:
    """Worker 退出前关闭用于读取队列深度的异步 Redis 客户端。"""

    global _queue_metrics_redis
    if _queue_metrics_redis is not None:
        await _queue_metrics_redis.aclose()
        _queue_metrics_redis = None


# Redis 和数据库都必须在共享事件循环关闭前释放；运行环境会统一安排顺序。
register_worker_cleanup(_close_queue_metrics_redis)
