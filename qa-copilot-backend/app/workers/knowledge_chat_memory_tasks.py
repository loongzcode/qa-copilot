"""由 Celery 执行的知识问答记忆压缩任务。"""
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionFactory
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_chat_repository import KnowledgeChatRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.services.knowledge_chat_memory_service import (
    KnowledgeChatMemoryService,
)
from app.workers.async_runtime import run_worker_coroutine


async def _run_memory_compression(session_id: int, task_id: str) -> bool:
    """为一次记忆压缩任务创建数据库 Session，并调用业务 Service。"""

    # Celery 任务不是 FastAPI 请求，不能使用 Depends(get_db)，
    # 因此需要在这里主动创建并管理数据库 Session。
    async with AsyncSessionFactory() as session:
        service = KnowledgeChatMemoryService(
            knowledge_chat_repository=KnowledgeChatRepository(session),
            ai_model_repository=AIModelRepository(session),
            prompt_template_repository=PromptTemplateRepository(session),
        )

        return await service.compress_session_memory(session_id, task_id)


@celery_app.task(
    bind=True,
    name="knowledge.compress_chat_memory",
    autoretry_for=(
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    ),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def compress_knowledge_chat_memory_task(
    self,
    session_id: int,
) -> bool:
    """
    Celery 同步入口：在 Worker 的事件循环中执行异步压缩业务。
        - name 必须和调度器发送的 knowledge.compress_chat_memory 完全一致。
        - autoretry_for 只对临时性的模型连接问题重试。
        - retry_backoff=True：重试间隔逐渐变长，避免连续轰炸模型服务。
        - retry_jitter=True：给重试时间增加随机偏移，避免大量任务同时重试。
        - max_retries=3：最多重试三次。
        - run_until_complete()：一直执行异步方法，直到得到 True、False 或抛出异常。
        self 是 bind=True 后由 Celery 传入的当前任务对象，这个方法暂时没有主动使用它，但保留它与项目现有任务结构一致。
    """

    # Celery 任务编号作为后台调用链标识。一次压缩中的摘要生成和摘要
    # Embedding 会写入同一个 task_id，方便在调用日志中一起查看。
    task_id = str(self.request.id)
    return run_worker_coroutine(
        _run_memory_compression(session_id, task_id)
    )
