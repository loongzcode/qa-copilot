from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionFactory
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_document_repository import KnowledgeDocumentRepository
from app.services.knowledge_document_index_service import KnowledgeDocumentIndexService
from app.storage import get_document_storage
from app.workers.async_runtime import run_worker_coroutine


async def _run_index(document_id: int, task_id: str) -> bool:
    async with AsyncSessionFactory() as session:
        service = KnowledgeDocumentIndexService(
            repository=KnowledgeDocumentRepository(session),
            ai_model_repository=AIModelRepository(session),
            document_storage=get_document_storage(),
        )
        return await service.index_document(document_id, task_id)


async def _delete_document_file(document_id: int, object_key: str) -> bool:
    """幂等删除知识文档的原始存储对象。

    功能：根据发件箱保存的对象键删除本地文件或 S3 对象；对象已经不存在也视为成功。

    作用：由 ``knowledge.delete_document_file`` Celery 任务调用，使 HTTP 删除请求
    不必等待磁盘或远程对象存储完成。

    为什么用它：文件删除发生在数据库事务提交之后，使用可重试后台任务能够
    缩短接口耗时，也能在进程中断后继续处理。``document_id`` 只用于日志和任务
    追踪，真正定位文件使用不可猜测的 ``object_key``。
    """

    del document_id
    storage = get_document_storage()
    await storage.delete_file(object_key)
    return True


@celery_app.task(
    bind=True,
    name="knowledge.index_document",
    autoretry_for=(
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
        OSError,
    ),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def index_knowledge_document_task(self, document_id: int) -> bool:
    """Celery 同步入口；同一 Worker 复用事件循环，每个任务新建 Session。"""

    # bind=True 后可以从 self.request.id 取得 Celery 为本次任务生成的编号。
    # 自动重试仍沿用这个编号，因此多次尝试产生的 AI 日志可以串在一起。
    task_id = str(self.request.id)
    return run_worker_coroutine(
        _run_index(document_id, task_id)
    )


@celery_app.task(
    name="knowledge.delete_document_file",
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
)
def delete_knowledge_document_file_task(
        document_id: int,
        object_key: str,
) -> bool:
    """Celery 文件清理入口；临时存储故障时自动退避重试。"""

    return run_worker_coroutine(
        _delete_document_file(document_id, object_key)
    )
