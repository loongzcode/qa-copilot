"""知识文档分批暂存和原子发布的 PostgreSQL 集成测试。"""

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
    KnowledgeDocumentChunkStaging,
)
from app.repositories.knowledge_document_repository import (  # noqa: E402
    KnowledgeDocumentRepository,
)
from app.repositories.knowledge_search_repository import (  # noqa: E402
    KnowledgeSearchRepository,
)


def _staged_chunk(
    document_id: int,
    task_id: str,
    chunk_index: int,
    model_id: int,
) -> KnowledgeDocumentChunkStaging:
    """创建一条带合法 1536 维向量的暂存测试数据。"""

    vector = [0.0] * KNOWLEDGE_EMBEDDING_DIMENSIONS
    vector[chunk_index] = 1.0
    return KnowledgeDocumentChunkStaging(
        document_id=document_id,
        task_id=task_id,
        chunk_index=chunk_index,
        content=f"new staged chunk {chunk_index}",
        token_count=4,
        page_no=chunk_index + 1,
        section_title=f"section {chunk_index}",
        chunk_metadata={"batch_test": True},
        embedding_model_id=model_id,
        embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
        index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
        embedding=vector,
    )


async def main() -> None:
    """验证错误任务不能发布，正确任务一次替换正式索引并清空暂存区。"""

    document_id: int | None = None
    task_id = "staging-integration-task"
    try:
        async with AsyncSessionFactory() as session:
            knowledge_base = await session.scalar(select(KnowledgeBase).limit(1))
            if knowledge_base is None or knowledge_base.embedding_model_id is None:
                raise RuntimeError("集成测试至少需要一个配置 Embedding 模型的知识库")

            document = KnowledgeDocument(
                knowledge_base_id=knowledge_base.id,
                document_type="OTHER",
                title="chunk-staging-integration-smoke",
                source_type="MANUAL",
                parse_status="INDEXING",
                index_task_id=task_id,
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
                    content="old live chunk",
                    token_count=3,
                    chunk_metadata={},
                    embedding=[1.0]
                    + [0.0] * (KNOWLEDGE_EMBEDDING_DIMENSIONS - 1),
                    embedding_model_id=knowledge_base.embedding_model_id,
                    embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                    index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
                )
            )
            await session.commit()
            model_id = knowledge_base.embedding_model_id

        async with AsyncSessionFactory() as session:
            repository = KnowledgeDocumentRepository(session)
            assert await repository.append_staged_chunks(
                document_id,
                task_id,
                [_staged_chunk(document_id, task_id, 0, model_id)],
            )
            assert await repository.append_staged_chunks(
                document_id,
                task_id,
                [
                    _staged_chunk(document_id, task_id, 1, model_id),
                    _staged_chunk(document_id, task_id, 2, model_id),
                ],
            )

        async with AsyncSessionFactory() as session:
            repository = KnowledgeDocumentRepository(session)
            assert not await repository.publish_staged_chunks(
                document_id,
                "obsolete-task",
                3,
            )
            live_contents = list(
                (
                    await session.scalars(
                        select(KnowledgeDocumentChunk.content).where(
                            KnowledgeDocumentChunk.document_id == document_id
                        )
                    )
                ).all()
            )
            staged_count = await session.scalar(
                select(func.count(KnowledgeDocumentChunkStaging.id)).where(
                    KnowledgeDocumentChunkStaging.document_id == document_id
                )
            )
            assert live_contents == ["old live chunk"]
            assert staged_count == 3

            # 文档正在重建时，兼容的旧正式切片仍应参与检索；暂存切片不能参与。
            candidates = await KnowledgeSearchRepository(session).vector_search(
                knowledge_base_id=knowledge_base.id,
                query_vector=[1.0]
                + [0.0] * (KNOWLEDGE_EMBEDDING_DIMENSIONS - 1),
                embedding_model_id=model_id,
                embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
                limit=100,
            )
            assert document_id in {
                candidate.document_id for candidate in candidates
            }
            full_text_candidates = await KnowledgeSearchRepository(
                session
            ).full_text_search(
                knowledge_base_id=knowledge_base.id,
                query_text="old live chunk",
                embedding_model_id=model_id,
                embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
                index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
                limit=100,
            )
            assert document_id in {
                candidate.document_id for candidate in full_text_candidates
            }

        async with AsyncSessionFactory() as session:
            repository = KnowledgeDocumentRepository(session)
            assert await repository.publish_staged_chunks(document_id, task_id, 3)

        async with AsyncSessionFactory() as session:
            document = await session.get(KnowledgeDocument, document_id)
            live_contents = list(
                (
                    await session.scalars(
                        select(KnowledgeDocumentChunk.content)
                        .where(KnowledgeDocumentChunk.document_id == document_id)
                        .order_by(KnowledgeDocumentChunk.chunk_index)
                    )
                ).all()
            )
            staged_count = await session.scalar(
                select(func.count(KnowledgeDocumentChunkStaging.id)).where(
                    KnowledgeDocumentChunkStaging.document_id == document_id
                )
            )
            assert document is not None and document.parse_status == "READY"
            assert live_contents == [
                "new staged chunk 0",
                "new staged chunk 1",
                "new staged chunk 2",
            ]
            assert staged_count == 0

        print(
            "Knowledge chunk staging smoke passed:",
            {
                "obsolete_task_blocked": True,
                "old_index_preserved_before_publish": True,
                "old_index_searchable_during_rebuild": True,
                "published_chunk_count": 3,
                "staging_cleaned": True,
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
