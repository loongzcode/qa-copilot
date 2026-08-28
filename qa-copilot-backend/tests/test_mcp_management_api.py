"""MCP 管理页接口注册和权限依赖测试。"""

from app.api.mcp_management_api import router


def test_mcp_management_routes_are_registered_with_permissions() -> None:
    routes = {route.path: route for route in router.routes}

    assert "/mcp-management/info" in routes
    assert "/mcp-management/tools/{tool_code}/call" in routes
    assert "GET" in routes["/mcp-management/info"].methods
    assert "POST" in routes["/mcp-management/tools/{tool_code}/call"].methods
