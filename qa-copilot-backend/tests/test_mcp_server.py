"""Model Context Protocol（模型上下文协议）认证、发现和权限边界测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core.permissions import Permission
from app.exceptions import BadRequestException
from app.mcp_server import (
    MCP_HTTP_APP,
    MCP_SERVER,
    ApplicationTokenVerifier,
    execute_mcp_capability,
)
from app.schemas.vo.mcp_management import McpToolCallResultVO
from fastapi.testclient import TestClient
from mcp.server.auth.provider import AccessToken
from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared.memory import create_connected_server_and_client_session


async def test_mcp_tool_discovery_only_exposes_allowlisted_read_only_tool() -> None:
    """MCP 客户端只能发现能力目录中显式开放的只读工具，不能看到写能力。"""

    async with create_connected_server_and_client_session(MCP_SERVER) as session:
        result = await session.list_tools()

    tools = {tool.name: tool for tool in result.tools}
    assert set(tools) == {
        "quality_delivery.get_status",
        "project.list_accessible",
        "requirement.get_detail",
        "test_case.list",
    }
    assert all(tool.annotations is not None for tool in tools.values())
    assert all(tool.annotations.readOnlyHint is True for tool in tools.values())
    assert "test_case.generate_missing" not in tools


def test_mcp_streamable_http_authenticated_discovery_and_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 入口拒绝匿名请求，并允许有效令牌完成发现和只读调用。"""

    async def accept_token(_: object, token: str) -> AccessToken:
        return AccessToken(
            token=token,
            client_id="pytest-client",
            subject="9",
            scopes=[Permission.REQUIREMENT_VIEW],
        )

    async def fake_execute(_: str, arguments: dict[str, object]) -> dict[str, object]:
        return {
            "stage": "HUMAN_REQUIREMENT_REVIEW",
            "projectId": arguments["project_id"],
        }

    headers = {
        "Authorization": "Bearer test-access-token",
        "Accept": "application/json, text/event-stream",
    }

    # 使用 SDK 默认允许的 localhost Host，保留 DNS rebinding（域名重绑定）防护。
    with TestClient(MCP_HTTP_APP, base_url="http://localhost:8000") as client:
        unauthorized = client.post(
            "/",
            headers={"Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "anonymous", "version": "1.0"},
                },
            },
        )
        assert unauthorized.status_code == 401

        monkeypatch.setattr(ApplicationTokenVerifier, "verify_token", accept_token)
        monkeypatch.setattr("app.mcp_server.execute_mcp_capability", fake_execute)
        initialize = client.post(
            "/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1.0"},
                },
            },
        )
        assert initialize.status_code == 200
        protocol_version = initialize.json()["result"]["protocolVersion"]
        protocol_headers = {
            **headers,
            "Mcp-Protocol-Version": protocol_version,
        }
        tools = client.post(
            "/",
            headers=protocol_headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        called = client.post(
            "/",
            headers=protocol_headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "quality_delivery.get_status",
                    "arguments": {"project_id": 8, "requirement_id": 12},
                },
            },
        )

    assert tools.status_code == 200
    assert {item["name"] for item in tools.json()["result"]["tools"]} == {
        "quality_delivery.get_status",
        "project.list_accessible",
        "requirement.get_detail",
        "test_case.list",
    }
    assert called.status_code == 200
    assert called.json()["result"]["structuredContent"]["stage"] == "HUMAN_REQUIREMENT_REVIEW"


async def test_invalid_application_token_is_rejected() -> None:
    """非平台签发或已损坏的令牌不能转换成 MCP AccessToken。"""

    assert await ApplicationTokenVerifier().verify_token("invalid-token") is None


class _SessionContext:
    """为 MCP Service 单元测试提供不连接真实数据库的异步 Session 上下文。"""

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_: object) -> None:
        return None


async def test_mcp_transport_delegates_to_shared_management_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """协议入口只负责认证和传输，实际调用必须委托给共用管理 Service。"""

    user = SimpleNamespace(id=9, is_superuser=True, roles=[])

    async def load_user() -> object:
        return user

    service = SimpleNamespace(
        call_tool=AsyncMock(
            return_value=McpToolCallResultVO(
                tool_code="quality_delivery.get_status",
                result={"stage": "HUMAN_REQUIREMENT_REVIEW"},
            )
        )
    )
    monkeypatch.setattr("app.mcp_server._load_current_mcp_user", load_user)
    monkeypatch.setattr("app.mcp_server.AsyncSessionFactory", _SessionContext)
    monkeypatch.setattr(
        "app.mcp_server.get_mcp_management_service",
        lambda _: service,
    )

    result = await execute_mcp_capability(
        "quality_delivery.get_status",
        {"project_id": 8, "requirement_id": 12},
    )

    assert result == {"stage": "HUMAN_REQUIREMENT_REVIEW"}
    service.call_tool.assert_awaited_once_with(
        "quality_delivery.get_status",
        {"project_id": 8, "requirement_id": 12},
        user,
    )


async def test_mcp_transport_converts_business_error_to_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """业务权限错误应成为 MCP ToolError，而不是泄漏 Python 堆栈。"""

    user = SimpleNamespace(id=9, is_superuser=True, roles=[])

    async def load_user() -> object:
        return user

    service = SimpleNamespace(
        call_tool=AsyncMock(
            side_effect=BadRequestException("工具不存在或不允许从 MCP 调用")
        )
    )
    monkeypatch.setattr("app.mcp_server._load_current_mcp_user", load_user)
    monkeypatch.setattr("app.mcp_server.AsyncSessionFactory", _SessionContext)
    monkeypatch.setattr(
        "app.mcp_server.get_mcp_management_service",
        lambda _: service,
    )

    with pytest.raises(ToolError, match="不允许从 MCP 调用"):
        await execute_mcp_capability("system.delete_all", {})
