"""把已经写入数据库的需求拆解任务投递给 Celery。"""

import asyncio

from app.core.celery_app import celery_app


async def enqueue_requirement_extraction(
    extraction_task_id: int,
    celery_task_id: str,
) -> str:
    """把已持久化的需求拆解任务投递到 Celery。

    功能：在线程中调用 Celery ``send_task``，携带数据库任务 ID，并复用提交阶段
    预生成的 celery_task_id。
    作用：由需求拆解提交 Service 在数据库 commit 后调用，通知 Worker 领取已经
    存在的业务任务，同时返回 Celery 实际使用的 ID 供一致性确认。
    为什么用它：Celery 投递 API 是同步网络调用，使用 ``asyncio.to_thread`` 可
    避免阻塞 FastAPI 事件循环；先生成并复用同一任务 ID，能稳定关联 PostgreSQL
    记录与 Redis 消息。替代的事务 Outbox 可靠性更强，但当前投递失败会由 Service
    立即把任务标记为 FAILED。
    """

    result = await asyncio.to_thread(
        celery_app.send_task,
        "requirement.extract_items",
        args=[extraction_task_id],
        task_id=celery_task_id,
        retry=False,
    )
    return str(result.id)
