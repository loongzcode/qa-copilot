"""把已持久化的缺失用例生成任务投递给 Celery。"""

import asyncio

from app.core.celery_app import celery_app


async def enqueue_case_generation(project_id: int, generation_task_id: int) -> str:
    """投递一条缺失用例生成消息并返回 Celery 任务 ID。

    功能：向 ``case.generate_missing`` 任务发送项目 ID 和数据库任务 ID。
    作用：由 HTTP Service 在数据库任务提交后调用，让专用 Worker 开始执行。
    为什么用它：Celery send_task 是同步网络调用，放入线程可避免阻塞 FastAPI
    事件循环；数据库主键作为业务幂等键，重复消息也只能领取一次任务。
    """
    result = await asyncio.to_thread(
        celery_app.send_task,
        "case.generate_missing",
        args=[project_id, generation_task_id],
        retry=False,
    )
    return str(result.id)
