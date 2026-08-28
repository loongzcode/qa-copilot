import asyncio
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.config import settings
from app.core.constants import (
    KNOWLEDGE_DOCUMENT_INDEX_VERSION,
    AIModelTaskType,
    KnowledgeDocumentParseStatus,
)
from app.core.metrics import record_knowledge_index_run
from app.exceptions.errors import describe_exception
from app.models import KnowledgeDocumentChunkStaging
from app.rag import (
    iter_document_chunks,
    iter_document_sections,
    take_chunk_batch,
)
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_document_repository import KnowledgeDocumentRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.storage import DocumentStorage
from app.utils.ai_client_util import generate_embeddings


class KnowledgeDocumentIndexService:
    """Worker 使用的文档解析、切片和向量索引业务服务。"""

    def __init__(
        self,
        repository: KnowledgeDocumentRepository,
        ai_model_repository: AIModelRepository,
        document_storage: DocumentStorage,
    ) -> None:
        self.repository = repository
        self.ai_model_repository = ai_model_repository
        self.document_storage = document_storage

    async def index_document(self, document_id: int, task_id: str) -> bool:
        """以有界内存完成文档索引；重复或过期任务返回 False。

        功能：流式解析文档，按固定批次切片、生成向量并写入暂存表，最后原子
        发布完整索引。
        作用：这是 Celery Worker 处理知识文档的主流水线，连接对象存储、解析器、
        Embedding 模型和 PostgreSQL 正式切片表。
        为什么用它：大文档若一次保存全部段落、切片、向量和 ORM 实体，内存会
        随文档大小增长；分批暂存使内存主要由单个解析段和单个模型批次决定，
        同时确保中途失败不会覆盖旧的可用索引。
        """

        started_at = time.perf_counter()

        # 行锁保证同一文档即使被重复投递，也只有一个 Worker 能从
        # PENDING/FAILED 推进到 PARSING，其余重复任务直接结束。
        document = await self.repository.claim_document_for_index(
            document_id,
            task_id,
        )
        if document is None:
            record_knowledge_index_run(
                result="skipped",
                duration_seconds=time.perf_counter() - started_at,
            )
            return False

        # 文档索引发生在 Celery Worker 中，没有 HTTP request_id。文档记录
        # 可以提供上传用户，知识库可以提供项目，Celery 自身提供任务 ID。
        # 同一文档分成多个 Embedding 批次时，这些日志会共用同一 task_id。
        usage_context = AIUsageContextDTO(
            user_id=document.created_by,
            project_id=document.knowledge_base.project_id,
            task_id=task_id,
        )

        try:
            if not document.object_key:
                raise ValueError("文档没有可读取的对象存储地址")

            knowledge_base = document.knowledge_base
            embedding_model = knowledge_base.embedding_model
            provider = embedding_model.provider
            if not knowledge_base.enabled:
                raise ValueError("知识库已停用，不能继续建立索引")
            if not embedding_model.enabled or not provider.enabled:
                raise ValueError("知识库配置的 Embedding 模型或服务商已停用")
            if AIModelTaskType.EMBEDDING.value not in embedding_model.task_types:
                raise ValueError("知识库配置的模型不支持 Embedding")

            extension = Path(document.original_filename or document.object_key).suffix.lower()
            with TemporaryDirectory(prefix="qa-copilot-index-") as temp_dir:
                local_path = Path(temp_dir) / f"source{extension}"
                await self.document_storage.download_file(document.object_key, local_path)
                if not await self.repository.touch_index_heartbeat(
                    document_id,
                    task_id,
                ):
                    raise RuntimeError("索引任务已失去执行权，停止旧 Worker")

                # 生成器在调用 next() 时才真正读取文件。take_chunk_batch 会在线程
                # 中消费它，避免 PDF/DOCX 同步解析阻塞 Worker 的异步事件循环。
                sections = iter_document_sections(
                    local_path,
                    extension,
                    max_section_chars=settings.knowledge_document_section_max_chars,
                )
                chunk_stream = iter_document_chunks(
                    sections,
                    chunk_size=settings.knowledge_document_chunk_size_tokens,
                    chunk_overlap=settings.knowledge_document_chunk_overlap_tokens,
                )

                total_chunks = 0
                total_index_tokens = 0
                entered_indexing = False
                batch_size = settings.knowledge_embedding_batch_size

                while True:
                    batch = await asyncio.to_thread(
                        take_chunk_batch,
                        chunk_stream,
                        batch_size,
                    )
                    if not batch:
                        break

                    next_chunk_count = total_chunks + len(batch)
                    next_token_count = total_index_tokens + sum(
                        chunk.token_count for chunk in batch
                    )
                    if next_chunk_count > settings.knowledge_document_max_chunks:
                        raise ValueError(
                            "文档切片数量超过配置上限 "
                            f"{settings.knowledge_document_max_chunks}，请拆分文档后重试"
                        )
                    if next_token_count > settings.knowledge_document_max_index_tokens:
                        raise ValueError(
                            "文档索引 Token 数超过配置上限 "
                            f"{settings.knowledge_document_max_index_tokens}，"
                            "请拆分文档后重试"
                        )

                    if not entered_indexing:
                        if not await self.repository.mark_parse_status(
                            document_id,
                            task_id,
                            KnowledgeDocumentParseStatus.INDEXING.value,
                        ):
                            raise RuntimeError(
                                "索引任务已失去执行权，不能进入向量化阶段"
                            )
                        entered_indexing = True
                    elif not await self.repository.touch_index_heartbeat(
                        document_id,
                        task_id,
                    ):
                        raise RuntimeError("索引任务已失去执行权，停止旧 Worker")

                    result = await generate_embeddings(
                        repository=self.ai_model_repository,
                        provider=provider,
                        model=embedding_model,
                        input_texts=[chunk.content for chunk in batch],
                        task_type=AIModelTaskType.EMBEDDING.value,
                        usage_context=usage_context,
                    )
                    if len(result.vectors) != len(batch):
                        raise RuntimeError("生成的向量数量与当前切片批次数量不一致")

                    # entities 和 result.vectors 都只在本轮循环存活。提交后下一轮
                    # 会替换这些局部变量，不会累计整篇文档的向量。
                    entities = [
                        KnowledgeDocumentChunkStaging(
                            document_id=document_id,
                            task_id=task_id,
                            chunk_index=chunk.chunk_index,
                            content=chunk.content,
                            token_count=chunk.token_count,
                            page_no=chunk.page_no,
                            section_title=chunk.section_title,
                            chunk_metadata=chunk.metadata,
                            embedding=vector,
                            embedding_model_id=embedding_model.id,
                            embedding_dimensions=len(vector),
                            index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
                        )
                        for chunk, vector in zip(batch, result.vectors, strict=True)
                    ]
                    if not await self.repository.append_staged_chunks(
                        document_id,
                        task_id,
                        entities,
                    ):
                        raise RuntimeError("索引任务已失去执行权，不能暂存知识切片")

                    total_chunks = next_chunk_count
                    total_index_tokens = next_token_count

            if total_chunks == 0:
                # 没有切片的文档不能标记 READY，否则版本协调扫描会一直认为它
                # “缺少索引”并重复排队。进入 FAILED 后由用户检查原文件内容。
                raise ValueError("文档解析后没有可供索引的文本内容")

            if not await self.repository.publish_staged_chunks(
                document_id,
                task_id,
                total_chunks,
            ):
                raise RuntimeError("索引任务已失去执行权，不能发布知识切片")
            record_knowledge_index_run(
                result="success",
                duration_seconds=time.perf_counter() - started_at,
            )
            return True
        except Exception as exc:
            await self.repository.rollback()
            error_message = describe_exception(exc)[:4000]
            try:
                # 失败只清理当前任务的工作区，旧正式索引仍可继续服务检索。
                await self.repository.discard_staged_chunks(document_id, task_id)
            except Exception:
                await self.repository.rollback()
            try:
                await self.repository.mark_parse_status(
                    document_id,
                    task_id,
                    KnowledgeDocumentParseStatus.FAILED.value,
                    error_message,
                )
            except Exception:
                await self.repository.rollback()
            record_knowledge_index_run(
                result="failed",
                duration_seconds=time.perf_counter() - started_at,
            )
            raise
