"""MCP 管理页面使用的普通 FastAPI 接口。"""

from fastapi import APIRouter, Depends, Path

from app.api.service_deps.mcp_management import McpManagementServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, success
from app.schemas.dto.mcp_management import McpToolCallDTO
from app.schemas.vo.mcp_management import McpServerInfoVO, McpToolCallResultVO

router = APIRouter(prefix="/mcp-management", tags=["MCP 管理"])


@router.get(
    "/info",
    response_model=ApiResult[McpServerInfoVO],
    dependencies=[Depends(require_permission(Permission.MCP_VIEW))],
)
async def get_mcp_server_info(
    current_user: CurrentUser,
    service: McpManagementServiceDep,
) -> ApiResult[McpServerInfoVO]:
    """返回 MCP 地址、认证方式和当前用户有权使用的工具。"""

    return success(service.get_server_info(current_user))


@router.post(
    "/tools/{tool_code}/call",
    response_model=ApiResult[McpToolCallResultVO],
    dependencies=[Depends(require_permission(Permission.MCP_INVOKE))],
)
async def call_mcp_tool(
    payload: McpToolCallDTO,
    current_user: CurrentUser,
    service: McpManagementServiceDep,
    tool_code: str = Path(min_length=1, max_length=120),
) -> ApiResult[McpToolCallResultVO]:
    """在管理页内试调用工具；仍会校验工具对应的业务权限和项目权限。"""

    return success(await service.call_tool(tool_code, payload.arguments, current_user))
