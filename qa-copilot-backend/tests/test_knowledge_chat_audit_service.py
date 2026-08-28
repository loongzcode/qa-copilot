"""知识问答独立审计权限和游标分页测试。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.exceptions import NotFoundException
from app.services.knowledge_chat_audit_service import KnowledgeChatAuditService


def audit_session() -> SimpleNamespace:
    """创建带用户名的会话行，模拟 Repository 已加载 user 关系。"""
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=7,
        project_id=3,
        knowledge_base_id=5,
        user_id=11,
        user=SimpleNamespace(username="audited-user"),
        title="文章发布咨询",
        status="ACTIVE",
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )


def audit_message(message_id: int) -> SimpleNamespace:
    """创建一条最小审计消息，用于验证返回顺序和下一页游标。"""
    return SimpleNamespace(
        id=message_id,
        session_id=7,
        role="USER",
        content=f"问题 {message_id}",
        citations=[],
        model_id=None,
        prompt_template_id=None,
        status="SUCCESS",
        token_count=3,
        error_message=None,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_audit_session_list_includes_owner_name() -> None:
    """审计列表必须标识会话创建人，普通会话所有权查询不能替代该接口。"""
    repository = SimpleNamespace(list_audit_sessions=AsyncMock(return_value=([audit_session()], 1)))
    project_repository = SimpleNamespace(get_accessible_project=AsyncMock(return_value=object()))
    service = KnowledgeChatAuditService(repository, project_repository)

    result = await service.list_sessions(
        3,
        SimpleNamespace(id=1),
        knowledge_base_id=None,
        user_id=None,
        status=None,
        current=1,
        size=20,
    )

    assert result.total == 1
    assert result.records[0].user_name == "audited-user"


@pytest.mark.asyncio
async def test_audit_messages_return_oldest_id_as_next_cursor() -> None:
    """当前批次还有更早消息时，用最小消息 ID 作为下一次 beforeId。"""
    repository = SimpleNamespace(
        get_project_session=AsyncMock(return_value=audit_session()),
        list_messages=AsyncMock(return_value=([audit_message(21), audit_message(22)], True)),
    )
    project_repository = SimpleNamespace(get_accessible_project=AsyncMock(return_value=object()))
    service = KnowledgeChatAuditService(repository, project_repository)

    result = await service.list_messages(3, 7, SimpleNamespace(id=1), before_id=23, limit=2)

    assert result.has_more is True
    assert result.next_cursor == 21
    repository.list_messages.assert_awaited_once_with(7, 23, 2)


@pytest.mark.asyncio
async def test_audit_rejects_inaccessible_project() -> None:
    """即使用户有审计按钮权限，也不能跨越项目数据权限读取会话。"""
    repository = SimpleNamespace()
    project_repository = SimpleNamespace(get_accessible_project=AsyncMock(return_value=None))
    service = KnowledgeChatAuditService(repository, project_repository)

    with pytest.raises(NotFoundException, match="无权审计"):
        await service.list_sessions(
            3,
            SimpleNamespace(id=1),
            knowledge_base_id=None,
            user_id=None,
            status=None,
            current=1,
            size=20,
        )
