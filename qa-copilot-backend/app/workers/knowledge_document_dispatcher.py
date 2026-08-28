import asyncio

from app.core.celery_app import celery_app


async def enqueue_knowledge_document_index(document_id: int) -> str:
    """在线程中向 Celery 投递索引任务，避免阻塞 FastAPI 事件循环。"""

    result = await asyncio.to_thread(
        celery_app.send_task,
        "knowledge.index_document",
        args=[document_id],
        retry=False,
    )
    return str(result.id)
