"""Embedding 模型或索引版本变化后的重建检测集成测试。"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import delete, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.constants import (  # noqa: E402
    KNOWLEDGE_DOCUMENT_INDEX_VERSION,
    KNOWLEDGE_EMBEDDING_DIMENSIONS,
)
from app.core.database import AsyncSessionFactory, engine  # noqa: E402
from app.models import (  # noqa: E402
    AIModel,
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeDocumentChunk,
    OutboxEvent,
)
from app.repositories.knowledge_document_repository import (  # noqa: E402
    KnowledgeDocumentRepository,
)


async def main() -> None:
    """验证兼容、模型变化、版本变化和已排队四种文档的选择结果。"""

    document_ids: list[int] = []
    event_ids: list[int] = []
    vector = [0.0] * KNOWLEDGE_EMBEDDING_DIMENSIONS
    vector[0] = 1.0

    try:
        async with AsyncSessionFactory() as session:
            knowledge_base = await session.scalar(select(KnowledgeBase).limit(1))
            if knowledge_base is None:
                raise RuntimeError("集成测试至少需要一个知识库")
            alternate_model_id = await session.scalar(
                select(AIModel.id)
                .where(AIModel.id != knowledge_base.embedding_model_id)
                .limit(1)
            )

            documents = [
                KnowledgeDocument(
                    knowledge_base_id=knowledge_base.id,
                    document_type="OTHER",
                    title="reindex-compatible-smoke",
                    source_type="MANUAL",
                    parse_status="READY",
                    index_recovery_count=0,
                    document_metadata={},
                ),
                KnowledgeDocument(
                    knowledge_base_id=knowledge_base.id,
                    document_type="OTHER",
                    title="reindex-model-changed-smoke",
                    source_type="MANUAL",
                    parse_status="READY",
                    index_recovery_count=0,
                    document_metadata={},
                ),
                KnowledgeDocument(
                    knowledge_base_id=knowledge_base.id,
                    document_type="OTHER",
                    title="reindex-version-changed-smoke",
                    source_type="MANUAL",
                    parse_status="READY",
                    index_recovery_count=0,
                    document_metadata={},
                ),
                KnowledgeDocument(
                    knowledge_base_id=knowledge_base.id,
                    document_type="OTHER",
                    title="reindex-already-queued-smoke",
                    source_type="MANUAL",
                    parse_status="READY",
                    index_recovery_count=0,
                    document_metadata={},
                ),
            ]
            session.add_all(documents)
            await session.flush()
            document_ids = [document.id for document in documents]

            compatible, model_changed, version_changed, already_queued = documents
            session.add_all(
                [
                    KnowledgeDocumentChunk(
                        document_id=compatible.id,
                        chunk_index=0,
                        content="compatible",
                        token_count=1,
                        chunk_metadata={},
                        embedding=vector,
                        embedding_model_id=knowledge_base.embedding_model_id,
                        embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                        index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
                    ),
                    KnowledgeDocumentChunk(
                        document_id=model_changed.id,
                        chunk_index=0,
                        content="model changed",
                        token_count=2,
                        chunk_metadata={},
                        embedding=vector,
                        # 如果开发库只有一个模型，NULL 同样表示原模型已经不存在，
                        # 必须按不兼容处理。
                        embedding_model_id=alternate_model_id,
                        embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                        index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
                    ),
                    KnowledgeDocumentChunk(
                        document_id=version_changed.id,
                        chunk_index=0,
                        content="version changed",
                        token_count=2,
                        chunk_metadata={},
                        embedding=vector,
                        embedding_model_id=knowledge_base.embedding_model_id,
                        embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                        index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION + 1,
                    ),
                    KnowledgeDocumentChunk(
                        document_id=already_queued.id,
                        chunk_index=0,
                        content="already queued",
                        token_count=2,
                        chunk_metadata={},
                        embedding=vector,
                        embedding_model_id=alternate_model_id,
                        embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                        index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
                    ),
                ]
            )
            active_event = OutboxEvent(
                event_type="KNOWLEDGE_DOCUMENT_INDEX",
                aggregate_type="KNOWLEDGE_DOCUMENT",
                aggregate_id=already_queued.id,
                payload={"document_id": already_queued.id},
                status="PENDING",
            )
            session.add(active_event)
            await session.commit()
            event_ids.append(active_event.id)

        async with AsyncSessionFactory() as session:
            selected = await KnowledgeDocumentRepository(
                session
            ).lock_documents_requiring_reindex(
                embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
                limit=1000,
            )
            selected_ids = {document.id for document in selected}
            await session.rollback()

        assert compatible.id not in selected_ids
        assert model_changed.id in selected_ids
        assert version_changed.id in selected_ids
        assert already_queued.id not in selected_ids
        print(
            "Knowledge reindex detection smoke passed:",
            {
                "compatible_ignored": compatible.id not in selected_ids,
                "model_change_detected": model_changed.id in selected_ids,
                "version_change_detected": version_changed.id in selected_ids,
                "active_event_not_duplicated": already_queued.id not in selected_ids,
            },
        )
    finally:
        async with AsyncSessionFactory() as session:
            if event_ids:
                await session.execute(
                    delete(OutboxEvent).where(OutboxEvent.id.in_(event_ids))
                )
            if document_ids:
                await session.execute(
                    delete(KnowledgeDocument).where(
                        KnowledgeDocument.id.in_(document_ids)
                    )
                )
            await session.commit()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
