"""文档索引 Service 写入切片兼容性元数据的单元测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.core.constants import KNOWLEDGE_DOCUMENT_INDEX_VERSION
from app.services.knowledge_document_index_service import (
    KnowledgeDocumentIndexService,
)


async def test_index_writes_compatibility_metadata() -> None:
    """新切片必须记录生成模型、实际维度和当前索引版本。"""

    provider = SimpleNamespace(id=8, enabled=True)
    embedding_model = SimpleNamespace(
        id=17,
        enabled=True,
        provider=provider,
        task_types=["embedding"],
    )
    knowledge_base = SimpleNamespace(
        project_id=3,
        enabled=True,
        embedding_model=embedding_model,
    )
    document = SimpleNamespace(
        id=23,
        created_by=5,
        object_key="knowledge/test/source.txt",
        original_filename="source.txt",
        knowledge_base=knowledge_base,
    )
    repository = SimpleNamespace(
        claim_document_for_index=AsyncMock(return_value=document),
        touch_index_heartbeat=AsyncMock(return_value=True),
        mark_parse_status=AsyncMock(return_value=True),
        append_staged_chunks=AsyncMock(return_value=True),
        publish_staged_chunks=AsyncMock(return_value=True),
        discard_staged_chunks=AsyncMock(),
        rollback=AsyncMock(),
    )
    storage = SimpleNamespace(download_file=AsyncMock())
    service = KnowledgeDocumentIndexService(
        repository=repository,
        ai_model_repository=SimpleNamespace(),
        document_storage=storage,
    )
    parsed_chunk = SimpleNamespace(
        chunk_index=0,
        content="测试切片",
        token_count=4,
        page_no=None,
        section_title="章节",
        metadata={},
    )
    vector = [0.0] * 1536
    temporary_directory = MagicMock()
    temporary_directory.__enter__.return_value = "."
    temporary_directory.__exit__.return_value = False

    with (
        patch(
            "app.services.knowledge_document_index_service.TemporaryDirectory",
            return_value=temporary_directory,
        ),
        patch(
            "app.services.knowledge_document_index_service.iter_document_sections",
            return_value=iter([SimpleNamespace()]),
        ),
        patch(
            "app.services.knowledge_document_index_service.iter_document_chunks",
            return_value=iter([parsed_chunk]),
        ),
        patch(
            "app.services.knowledge_document_index_service.generate_embeddings",
            new=AsyncMock(return_value=SimpleNamespace(vectors=[vector])),
        ),
    ):
        result = await service.index_document(23, "metadata-test-task")

    assert result is True
    saved_chunks = repository.append_staged_chunks.await_args.args[2]
    assert len(saved_chunks) == 1
    saved_chunk = saved_chunks[0]
    assert saved_chunk.embedding_model_id == 17
    assert saved_chunk.embedding_dimensions == 1536
    assert saved_chunk.index_version == KNOWLEDGE_DOCUMENT_INDEX_VERSION
    repository.publish_staged_chunks.assert_awaited_once_with(
        23,
        "metadata-test-task",
        1,
    )


async def test_empty_document_fails_instead_of_rebuild_loop() -> None:
    """解析不到正文时必须进入 FAILED，不能生成无切片的 READY 文档。"""

    document = SimpleNamespace(
        id=24,
        created_by=5,
        object_key="knowledge/test/empty.txt",
        original_filename="empty.txt",
        knowledge_base=SimpleNamespace(
            project_id=3,
            enabled=True,
            embedding_model=SimpleNamespace(
                id=17,
                enabled=True,
                provider=SimpleNamespace(id=8, enabled=True),
                task_types=["embedding"],
            ),
        ),
    )
    repository = SimpleNamespace(
        claim_document_for_index=AsyncMock(return_value=document),
        touch_index_heartbeat=AsyncMock(return_value=True),
        mark_parse_status=AsyncMock(return_value=True),
        append_staged_chunks=AsyncMock(return_value=True),
        publish_staged_chunks=AsyncMock(return_value=True),
        discard_staged_chunks=AsyncMock(),
        rollback=AsyncMock(),
    )
    temporary_directory = MagicMock()
    temporary_directory.__enter__.return_value = "."
    temporary_directory.__exit__.return_value = False
    service = KnowledgeDocumentIndexService(
        repository=repository,
        ai_model_repository=SimpleNamespace(),
        document_storage=SimpleNamespace(download_file=AsyncMock()),
    )

    with (
        patch(
            "app.services.knowledge_document_index_service.TemporaryDirectory",
            return_value=temporary_directory,
        ),
        patch(
            "app.services.knowledge_document_index_service.iter_document_sections",
            return_value=iter([SimpleNamespace()]),
        ),
        patch(
            "app.services.knowledge_document_index_service.iter_document_chunks",
            return_value=iter([]),
        ),
    ):
        try:
            await service.index_document(24, "empty-document-task")
        except ValueError as exc:
            assert "没有可供索引的文本内容" in str(exc)
        else:
            raise AssertionError("空文档没有按预期失败")

    repository.append_staged_chunks.assert_not_awaited()
    repository.publish_staged_chunks.assert_not_awaited()
    failed_call = repository.mark_parse_status.await_args
    assert failed_call.args[2] == "FAILED"


async def test_large_document_is_staged_in_embedding_sized_batches() -> None:
    """切片多于单批上限时，Service 必须逐批生成和暂存而非整篇累计。"""

    provider = SimpleNamespace(id=8, enabled=True)
    embedding_model = SimpleNamespace(
        id=17,
        enabled=True,
        provider=provider,
        task_types=["embedding"],
    )
    document = SimpleNamespace(
        id=25,
        created_by=5,
        object_key="knowledge/test/large.txt",
        original_filename="large.txt",
        knowledge_base=SimpleNamespace(
            project_id=3,
            enabled=True,
            embedding_model=embedding_model,
        ),
    )
    repository = SimpleNamespace(
        claim_document_for_index=AsyncMock(return_value=document),
        touch_index_heartbeat=AsyncMock(return_value=True),
        mark_parse_status=AsyncMock(return_value=True),
        append_staged_chunks=AsyncMock(return_value=True),
        publish_staged_chunks=AsyncMock(return_value=True),
        discard_staged_chunks=AsyncMock(),
        rollback=AsyncMock(),
    )
    chunks = [
        SimpleNamespace(
            chunk_index=index,
            content=f"chunk-{index}",
            token_count=2,
            page_no=None,
            section_title=None,
            metadata={},
        )
        for index in range(25)
    ]

    async def fake_generate_embeddings(**kwargs):
        return SimpleNamespace(
            vectors=[[0.0] * 1536 for _ in kwargs["input_texts"]]
        )

    temporary_directory = MagicMock()
    temporary_directory.__enter__.return_value = "."
    temporary_directory.__exit__.return_value = False
    service = KnowledgeDocumentIndexService(
        repository=repository,
        ai_model_repository=SimpleNamespace(),
        document_storage=SimpleNamespace(download_file=AsyncMock()),
    )

    with (
        patch(
            "app.services.knowledge_document_index_service.TemporaryDirectory",
            return_value=temporary_directory,
        ),
        patch(
            "app.services.knowledge_document_index_service.iter_document_sections",
            return_value=iter([SimpleNamespace()]),
        ),
        patch(
            "app.services.knowledge_document_index_service.iter_document_chunks",
            return_value=iter(chunks),
        ),
        patch(
            "app.services.knowledge_document_index_service.generate_embeddings",
            new=AsyncMock(side_effect=fake_generate_embeddings),
        ) as embedding_mock,
    ):
        assert await service.index_document(25, "batch-test-task")

    staged_batch_sizes = [
        len(call.args[2]) for call in repository.append_staged_chunks.await_args_list
    ]
    model_batch_sizes = [
        len(call.kwargs["input_texts"]) for call in embedding_mock.await_args_list
    ]
    assert staged_batch_sizes == [20, 5]
    assert model_batch_sizes == [20, 5]
    repository.publish_staged_chunks.assert_awaited_once_with(
        25,
        "batch-test-task",
        25,
    )


async def test_document_over_token_limit_fails_before_model_call() -> None:
    """超过单篇 Token 上限时应停止调用模型并清理当前任务暂存数据。"""

    embedding_model = SimpleNamespace(
        id=17,
        enabled=True,
        provider=SimpleNamespace(id=8, enabled=True),
        task_types=["embedding"],
    )
    document = SimpleNamespace(
        id=26,
        created_by=5,
        object_key="knowledge/test/oversized.txt",
        original_filename="oversized.txt",
        knowledge_base=SimpleNamespace(
            project_id=3,
            enabled=True,
            embedding_model=embedding_model,
        ),
    )
    repository = SimpleNamespace(
        claim_document_for_index=AsyncMock(return_value=document),
        touch_index_heartbeat=AsyncMock(return_value=True),
        mark_parse_status=AsyncMock(return_value=True),
        append_staged_chunks=AsyncMock(return_value=True),
        publish_staged_chunks=AsyncMock(return_value=True),
        discard_staged_chunks=AsyncMock(),
        rollback=AsyncMock(),
    )
    oversized_chunk = SimpleNamespace(
        chunk_index=0,
        content="oversized",
        token_count=settings.knowledge_document_max_index_tokens + 1,
        page_no=None,
        section_title=None,
        metadata={},
    )
    temporary_directory = MagicMock()
    temporary_directory.__enter__.return_value = "."
    temporary_directory.__exit__.return_value = False
    service = KnowledgeDocumentIndexService(
        repository=repository,
        ai_model_repository=SimpleNamespace(),
        document_storage=SimpleNamespace(download_file=AsyncMock()),
    )

    with (
        patch(
            "app.services.knowledge_document_index_service.TemporaryDirectory",
            return_value=temporary_directory,
        ),
        patch(
            "app.services.knowledge_document_index_service.iter_document_sections",
            return_value=iter([SimpleNamespace()]),
        ),
        patch(
            "app.services.knowledge_document_index_service.iter_document_chunks",
            return_value=iter([oversized_chunk]),
        ),
        patch(
            "app.services.knowledge_document_index_service.generate_embeddings",
            new=AsyncMock(),
        ) as embedding_mock,
    ):
        try:
            await service.index_document(26, "token-limit-task")
        except ValueError as exc:
            assert "Token 数超过配置上限" in str(exc)
        else:
            raise AssertionError("超过 Token 上限的文档没有按预期失败")

    embedding_mock.assert_not_awaited()
    repository.append_staged_chunks.assert_not_awaited()
    repository.publish_staged_chunks.assert_not_awaited()
    repository.discard_staged_chunks.assert_awaited_once_with(
        26,
        "token-limit-task",
    )
