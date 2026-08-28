"""知识切片模型、维度和索引版本隔离的 PostgreSQL 集成测试。"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import delete, func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.constants import (  # noqa: E402
    KNOWLEDGE_DOCUMENT_INDEX_VERSION,
    KNOWLEDGE_EMBEDDING_DIMENSIONS,
)
from app.core.database import AsyncSessionFactory, engine  # noqa: E402
from app.models import (  # noqa: E402
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeDocumentChunk,
)
from app.repositories.knowledge_search_repository import (  # noqa: E402
    KnowledgeSearchRepository,
)


async def main() -> None:
    """构造三种元数据切片，验证两路检索只返回完全兼容的一条。"""

    document_id: int | None = None
    content = "metadata isolation unique phrase"
    vector = [0.0] * KNOWLEDGE_EMBEDDING_DIMENSIONS
    vector[0] = 1.0

    try:
        async with AsyncSessionFactory() as session:
            knowledge_base = await session.scalar(select(KnowledgeBase).limit(1))
            if knowledge_base is None:
                raise RuntimeError("集成测试至少需要一个知识库")

            document = KnowledgeDocument(
                knowledge_base_id=knowledge_base.id,
                document_type="OTHER",
                title="metadata-isolation-smoke",
                source_type="MANUAL",
                parse_status="READY",
                index_recovery_count=0,
                document_metadata={},
            )
            session.add(document)
            await session.flush()
            document_id = document.id

            compatible = KnowledgeDocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content=content,
                token_count=5,
                chunk_metadata={},
                embedding=vector,
                embedding_model_id=knowledge_base.embedding_model_id,
                embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
            )
            old_version = KnowledgeDocumentChunk(
                document_id=document.id,
                chunk_index=1,
                content=content,
                token_count=5,
                chunk_metadata={},
                embedding=vector,
                embedding_model_id=knowledge_base.embedding_model_id,
                embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION + 1,
            )
            unknown_model = KnowledgeDocumentChunk(
                document_id=document.id,
                chunk_index=2,
                content=content,
                token_count=5,
                chunk_metadata={},
                embedding=vector,
                embedding_model_id=None,
                embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
            )
            session.add_all([compatible, old_version, unknown_model])
            await session.commit()
            compatible_id = compatible.id
            incompatible_ids = {old_version.id, unknown_model.id}

        async with AsyncSessionFactory() as session:
            repository = KnowledgeSearchRepository(session)
            vector_results = await repository.vector_search(
                knowledge_base_id=knowledge_base.id,
                query_vector=vector,
                embedding_model_id=knowledge_base.embedding_model_id,
                embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
                limit=100,
            )
            full_text_results = await repository.full_text_search(
                knowledge_base_id=knowledge_base.id,
                query_text=content,
                embedding_model_id=knowledge_base.embedding_model_id,
                embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
                limit=100,
            )

            missing_metadata_count = await session.scalar(
                select(func.count(KnowledgeDocumentChunk.id)).where(
                    KnowledgeDocumentChunk.embedding_dimensions.is_(None)
                    | KnowledgeDocumentChunk.index_version.is_(None)
                )
            )

        vector_result_ids = {
            candidate.chunk_id for candidate in vector_results
        }
        full_text_result_ids = {
            candidate.chunk_id for candidate in full_text_results
        }
        assert compatible_id in vector_result_ids
        assert compatible_id in full_text_result_ids
        assert vector_result_ids.isdisjoint(incompatible_ids)
        assert full_text_result_ids.isdisjoint(incompatible_ids)
        assert missing_metadata_count == 0
        print(
            "Knowledge chunk metadata smoke passed:",
            {
                "compatible_chunk_id": compatible_id,
                "incompatible_chunk_ids": sorted(incompatible_ids),
                "vector_filter_passed": vector_result_ids.isdisjoint(
                    incompatible_ids
                ),
                "full_text_filter_passed": full_text_result_ids.isdisjoint(
                    incompatible_ids
                ),
                "missing_required_metadata": missing_metadata_count,
            },
        )
    finally:
        async with AsyncSessionFactory() as session:
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
