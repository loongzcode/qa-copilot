"""MCP 管理页和协议入口共用业务服务测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from app.core.permissions import Permission
from app.exceptions import BadRequestException, ForbiddenException
from app.services.mcp_management_service import McpManagementService


def _user_with_permissions(*permissions: str) -> SimpleNamespace:
    """构造一个拥有指定按钮权限的普通用户。"""

    return SimpleNamespace(
        id=9,
        is_superuser=False,
        roles=[
            SimpleNamespace(
                enabled=True,
                menus=[
                    SimpleNamespace(
                        enabled=True,
                        menu_type="button",
                        permission_code=permission,
                    )
                    for permission in permissions
                ],
            )
        ],
    )


def _service() -> McpManagementService:
    return McpManagementService(
        project_service=SimpleNamespace(list_projects=AsyncMock()),
        requirement_service=SimpleNamespace(get_requirement_detail=AsyncMock()),
        test_case_service=SimpleNamespace(list_test_cases=AsyncMock()),
        quality_delivery_service=SimpleNamespace(get_status=AsyncMock()),
    )


def test_server_info_only_lists_tools_with_realtime_business_permission() -> None:
    """管理页不会向用户展示其已经被撤销业务权限的工具。"""

    service = _service()
    user = _user_with_permissions(Permission.REQUIREMENT_VIEW)

    info = service.get_server_info(user)

    assert {tool.code for tool in info.tools} == {
        "quality_delivery.get_status",
        "requirement.get_detail",
    }
    assert all(tool.read_only for tool in info.tools)
    assert all(tool.input_schema for tool in info.tools)


async def test_call_tool_rejects_unknown_write_and_missing_permission() -> None:
    """未知能力、审批型写能力和实时缺权都不能通过管理页试调用。"""

    service = _service()
    user = _user_with_permissions()

    with pytest.raises(BadRequestException, match="不允许从 MCP 调用"):
        await service.call_tool("system.delete_all", {}, user)
    with pytest.raises(BadRequestException, match="不允许从 MCP 调用"):
        await service.call_tool(
            "test_case.generate_missing",
            {"project_id": 8, "requirement_id": 12},
            user,
        )
    with pytest.raises(ForbiddenException, match=Permission.REQUIREMENT_VIEW):
        await service.call_tool(
            "requirement.get_detail",
            {"project_id": 8, "requirement_id": 12},
            user,
        )


async def test_call_tool_routes_four_read_only_capabilities_to_existing_services() -> None:
    """四项 MCP 工具必须调用现有 Service，而不是直接访问数据库。"""

    project_service = SimpleNamespace(
        list_projects=AsyncMock(return_value=([{"id": 8, "name": "LBlog"}], 1))
    )
    requirement_result = SimpleNamespace(
        model_dump=Mock(return_value={"id": 12, "title": "发布文章"})
    )
    requirement_service = SimpleNamespace(
        get_requirement_detail=AsyncMock(return_value=requirement_result)
    )
    test_case_service = SimpleNamespace(
        list_test_cases=AsyncMock(return_value=([{"id": 31, "title": "发布成功"}], 1))
    )
    quality_result = SimpleNamespace(
        model_dump=Mock(return_value={"stage": "READY_FOR_AUTOMATION"})
    )
    quality_service = SimpleNamespace(get_status=AsyncMock(return_value=quality_result))
    service = McpManagementService(
        project_service,
        requirement_service,
        test_case_service,
        quality_service,
    )
    user = SimpleNamespace(id=1, is_superuser=True, roles=[])

    project_result = await service.call_tool("project.list_accessible", {}, user)
    requirement_result_vo = await service.call_tool(
        "requirement.get_detail",
        {"project_id": 8, "requirement_id": 12},
        user,
    )
    case_result = await service.call_tool(
        "test_case.list",
        {"project_id": 8, "current": 1, "size": 20},
        user,
    )
    quality_result_vo = await service.call_tool(
        "quality_delivery.get_status",
        {"project_id": 8, "requirement_id": 12},
        user,
    )

    assert project_result.result["total"] == 1
    assert requirement_result_vo.result["id"] == 12
    assert case_result.result["records"][0]["id"] == 31
    assert quality_result_vo.result["stage"] == "READY_FOR_AUTOMATION"
    requirement_service.get_requirement_detail.assert_awaited_once_with(8, 12, user)
    test_case_service.list_test_cases.assert_awaited_once_with(
        8,
        user,
        "",
        None,
        None,
        None,
        1,
        20,
    )
