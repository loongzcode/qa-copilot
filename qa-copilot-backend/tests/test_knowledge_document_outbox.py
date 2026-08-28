from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.models import KnowledgeDocument
from app.services.knowledge_document_service import KnowledgeDocumentService


async def test_submit_index_commits_document_and_outbox_once() -> None:
    """索引请求应先登记发件箱事件，再用一次提交保存两项修改。"""

    now = datetime.now(UTC)
    document = KnowledgeDocument(
        id=15,
        knowledge_base_id=3,
        module_id=None,
        document_type="REQUIREMENT",
        title="发布文章需求",
        source_type="UPLOAD",
        object_key="knowledge/3/2026/08/source.pdf",
        original_filename="source.pdf",
        version=1,
        parse_status="READY",
        index_recovery_count=0,
        document_metadata={},
        created_by=1,
        created_at=now,
        updated_at=now,
    )
    document.chunk_count = 6

    operation_order: list[str] = []
    repository = SimpleNamespace(
        get_document=AsyncMock(side_effect=[document, document]),
        commit=AsyncMock(side_effect=lambda: operation_order.append("commit")),
        rollback=AsyncMock(),
    )
    outbox_repository = SimpleNamespace(
        add_pending_event=Mock(
            side_effect=lambda **_: operation_order.append("add_outbox")
        )
    )
    knowledge_base_repository = SimpleNamespace(
        get_accessible_knowledge_base=AsyncMock(
            return_value=SimpleNamespace(enabled=True)
        )
    )
    service = KnowledgeDocumentService(
        repository=repository,
        outbox_event_repository=outbox_repository,
        knowledge_base_repository=knowledge_base_repository,
        test_modules_repository=SimpleNamespace(),
        document_storage=SimpleNamespace(),
    )

    result = await service.submit_index(
        project_id=8,
        knowledge_base_id=3,
        document_id=15,
        current_user=SimpleNamespace(),
    )

    assert result.parse_status == "PENDING"
    assert operation_order == ["add_outbox", "commit"]
    repository.commit.assert_awaited_once()
    outbox_repository.add_pending_event.assert_called_once_with(
        event_type="KNOWLEDGE_DOCUMENT_INDEX",
        aggregate_type="KNOWLEDGE_DOCUMENT",
        aggregate_id=15,
        payload={"document_id": 15},
    )
