"""知识文档删除链路的 PostgreSQL 与本地存储集成冒烟测试。"""

import asyncio
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import delete, func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionFactory, engine  # noqa: E402
from app.models import (  # noqa: E402
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeDocumentChunk,
    OutboxEvent,
)
from app.repositories.knowledge_document_repository import (  # noqa: E402
    KnowledgeDocumentRepository,
)
from app.repositories.outbox_event_repository import (  # noqa: E402
    OutboxEventRepository,
)
from app.services.knowledge_document_service import (  # noqa: E402
    KnowledgeDocumentService,
)
from app.services.outbox_event_service import OutboxEventService  # noqa: E402
from app.storage import LocalDocumentStorage  # noqa: E402
from app.workers.knowledge_document_tasks import (  # noqa: E402
    _delete_document_file,
)


class AccessibleKnowledgeBaseRepository:
    """测试替身：只返回测试已经选定的真实知识库。"""

    def __init__(self, knowledge_base: KnowledgeBase) -> None:
        self.knowledge_base = knowledge_base

    async def get_accessible_knowledge_base(
            self,
            project_id: int,
            knowledge_base_id: int,
            current_user: object,
    ) -> KnowledgeBase | None:
        del current_user
        if (
            self.knowledge_base.project_id == project_id
            and self.knowledge_base.id == knowledge_base_id
        ):
            return self.knowledge_base
        return None


async def main() -> None:
    """创建文件、切片和活动任务，删除后验证四类资源全部得到处理。"""

    document_id: int | None = None
    event_ids: list[int] = []
    object_key = f"integration-delete/{uuid4().hex}.txt"
    storage = LocalDocumentStorage(settings.knowledge_document_storage_dir)

    with NamedTemporaryFile(delete=False, suffix=".txt") as temporary_file:
        temporary_file.write(b"deletion integration smoke")
        temporary_path = Path(temporary_file.name)

    try:
        await storage.save_file(temporary_path, object_key)
        stored_path = storage._resolve_object_key(object_key)
        assert stored_path.is_file()

        async with AsyncSessionFactory() as session:
            knowledge_base = await session.scalar(select(KnowledgeBase).limit(1))
            if knowledge_base is None:
                raise RuntimeError("集成测试至少需要一个知识库")

            document = KnowledgeDocument(
                knowledge_base_id=knowledge_base.id,
                document_type="OTHER",
                title="delete-integration-smoke",
                source_type="UPLOAD",
                object_key=object_key,
                original_filename="delete-integration-smoke.txt",
                mime_type="text/plain",
                size_bytes=26,
                parse_status="INDEXING",
                index_task_id="obsolete-index-worker",
                index_recovery_count=0,
                document_metadata={},
            )
            session.add(document)
            await session.flush()
            document_id = document.id

            session.add(
                KnowledgeDocumentChunk(
                    document_id=document.id,
                    chunk_index=0,
                    content="需要在删除后从检索索引中消失的测试切片",
                    token_count=12,
                    chunk_metadata={},
                )
            )
            active_index_event = OutboxEvent(
                event_type="KNOWLEDGE_DOCUMENT_INDEX",
                aggregate_type="KNOWLEDGE_DOCUMENT",
                aggregate_id=document.id,
                payload={"document_id": document.id},
                status="PENDING",
            )
            session.add(active_index_event)
            await session.commit()
            event_ids.append(active_index_event.id)

        async with AsyncSessionFactory() as session:
            repository = KnowledgeDocumentRepository(session)
            service = KnowledgeDocumentService(
                repository=repository,
                outbox_event_repository=OutboxEventRepository(session),
                knowledge_base_repository=AccessibleKnowledgeBaseRepository(
                    knowledge_base
                ),
                test_modules_repository=SimpleNamespace(),
                document_storage=storage,
            )
            await service.delete_knowledge_document(
                project_id=knowledge_base.project_id,
                knowledge_base_id=knowledge_base.id,
                document_id=document_id,
                current_user=SimpleNamespace(id=knowledge_base.created_by),
            )

        async with AsyncSessionFactory() as session:
            deleted_document = await session.get(KnowledgeDocument, document_id)
            chunk_count = await session.scalar(
                select(func.count(KnowledgeDocumentChunk.id)).where(
                    KnowledgeDocumentChunk.document_id == document_id
                )
            )
            events = list(
                (
                    await session.scalars(
                        select(OutboxEvent)
                        .where(OutboxEvent.aggregate_id == document_id)
                        .order_by(OutboxEvent.id)
                    )
                ).all()
            )
            event_ids = [event.id for event in events]

        assert deleted_document is not None
        assert deleted_document.deleted_at is not None
        assert deleted_document.index_task_id is None
        assert chunk_count == 0
        assert len(events) == 2
        assert events[0].event_type == "KNOWLEDGE_DOCUMENT_INDEX"
        assert events[0].status == "FAILED"
        cleanup_event = events[1]
        assert cleanup_event.event_type == "KNOWLEDGE_DOCUMENT_FILE_DELETE"
        assert cleanup_event.status == "PENDING"

        message = OutboxEventService._build_celery_message(cleanup_event)
        assert message.task_name == "knowledge.delete_document_file"
        assert message.args == [document_id, object_key]

        await _delete_document_file(document_id, object_key)
        assert not stored_path.exists()
        print(
            "Knowledge document deletion smoke passed:",
            {
                "document_soft_deleted": True,
                "chunks_deleted": chunk_count == 0,
                "index_event_cancelled": events[0].status == "FAILED",
                "file_deleted": not stored_path.exists(),
            },
        )
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
        await storage.delete_file(object_key)
        async with AsyncSessionFactory() as session:
            if event_ids:
                await session.execute(
                    delete(OutboxEvent).where(OutboxEvent.id.in_(event_ids))
                )
            if document_id is not None:
                await session.execute(
                    delete(KnowledgeDocument).where(
                        KnowledgeDocument.id == document_id
                    )
                )
            await session.commit()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
