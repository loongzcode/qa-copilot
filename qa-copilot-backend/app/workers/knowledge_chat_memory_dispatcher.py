import asyncio

from app.core.celery_app import celery_app


async def enqueue_knowledge_chat_memory_compression(session_id: int) -> str:
    result =  await asyncio.to_thread(
        celery_app.send_task,
        "knowledge.compress_chat_memory",
        args=[session_id],
        retry = False,
    )
    return str(result.id)