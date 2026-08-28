"""QA Copilot 的 Model Context Protocol（模型上下文协议）服务端。

第一阶段只暴露能力目录中显式标记为 MCP 可用的只读能力。MCP 只是新的调用入口，
不会绕过现有用户权限、项目数据权限或业务 Service。
"""

from __future__ import annotations

from typing import Any

import jwt
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from app.api.service_deps.mcp_management import get_mcp_management_service
from app.core.config import settings
from app.core.constants import ProjectStatus, TestCaseSource, TestCaseStatus
from app.core.database import AsyncSessionFactory
from app.core.deps import get_permission_codes
from app.core.security import decode_token
from app.exceptions import BusinessException
from app.repositories.auth_repository import AuthRepository


class ApplicationTokenVerifier(TokenVerifier):
    """用平台现有 JSON Web Token（JSON 网络令牌）认证 MCP 请求。

    功能：校验 Bearer 访问令牌，并确认对应用户仍存在且已启用。
    作用：在 MCP 协议消息进入工具发现或工具调用前建立用户身份。
    为什么用它：复用平台登录令牌可保持账号生命周期一致；仅解码令牌而不查数据库会让
    已停用用户继续访问，所以认证阶段还会执行一次轻量用户查询。
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            payload = decode_token(token, "access")
            user_id = int(payload["sub"])
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
            return None

        async with AsyncSessionFactory() as session:
            user = await AuthRepository(session).get_by_id(
                user_id,
                with_permissions=True,
            )
            if user is None or not user.is_active:
                return None
            permission_codes = sorted(
                code for code in get_permission_codes(user) if code is not None
            )

        expires_at = payload.get("exp")
        return AccessToken(
            token=token,
            client_id=f"qa-copilot-user-{user_id}",
            subject=str(user_id),
            scopes=permission_codes,
            expires_at=int(expires_at) if expires_at is not None else None,
            resource=settings.mcp_resource_server_url,
        )


async def _load_current_mcp_user() -> Any:
    """按 MCP 认证上下文重新加载当前用户及其实时权限。

    功能：从 SDK 保存的请求级 AccessToken 中取得用户 ID，再查询最新用户状态。
    作用：为能力执行器提供与普通 FastAPI API 相同的 User 对象。
    为什么用它：连接建立后角色可能被管理员修改，调用时重新查询可以防止长期连接继续
    使用过期权限；替代方案是完全信任令牌中的 scopes，但撤权要等令牌过期才生效。
    """

    access_token = get_access_token()
    if access_token is None or access_token.subject is None:
        raise ToolError("MCP 请求缺少有效的用户身份")
    try:
        user_id = int(access_token.subject)
    except (TypeError, ValueError) as exc:
        raise ToolError("MCP 访问令牌中的用户标识无效") from exc

    async with AsyncSessionFactory() as session:
        user = await AuthRepository(session).get_by_id(
            user_id,
            with_permissions=True,
        )
        if user is None or not user.is_active:
            raise ToolError("用户不存在或已停用")
        return user


async def execute_mcp_capability(
    capability_code: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """通过共用能力白名单和业务 Service 执行一次 MCP 只读调用。

    功能：校验能力是否允许 MCP 调用、实时权限和参数，再查询业务结果。
    作用：它是 MCP 工具与内部业务层之间的唯一适配入口。
    为什么用它：显式白名单不会把 Repository 或任意 Python 函数暴露给外部客户端；
    项目访问判断继续由 QualityDeliveryService 完成，避免 MCP 产生第二套数据权限规则。
    """

    current_user = await _load_current_mcp_user()
    async with AsyncSessionFactory() as session:
        service = get_mcp_management_service(session)
        try:
            result = await service.call_tool(capability_code, arguments, current_user)
            return result.result
        except BusinessException as exc:
            raise ToolError(exc.message) from exc


MCP_SERVER = FastMCP(
    name="QA Copilot",
    instructions=(
        "仅提供 QA Copilot 能力目录中经过白名单审核的只读工具；"
        "所有调用仍受用户权限和项目数据权限限制。"
    ),
    token_verifier=ApplicationTokenVerifier(),
    auth=AuthSettings(
        issuer_url=settings.mcp_issuer_url,
        resource_server_url=settings.mcp_resource_server_url,
        required_scopes=[],
    ),
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
)


@MCP_SERVER.tool(
    name="quality_delivery.get_status",
    title="查询质量交付状态",
    description="查询指定需求当前处于需求拆解、人工确认、用例生成或自动化准备的哪个阶段。",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
async def get_quality_delivery_status(
    project_id: int,
    requirement_id: int,
) -> dict[str, Any]:
    """查询一个项目内指定需求的质量交付阶段，不创建或修改任何业务数据。"""

    return await execute_mcp_capability(
        "quality_delivery.get_status",
        {
            "project_id": project_id,
            "requirement_id": requirement_id,
        },
    )


@MCP_SERVER.tool(
    name="project.list_accessible",
    title="查询可访问项目",
    description="分页查询当前登录用户有权访问的测试项目。",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
async def list_accessible_projects(
    keyword: str = "",
    status: ProjectStatus | None = None,
    current: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """分页查询当前用户可访问项目，不返回项目密钥或环境变量。"""

    return await execute_mcp_capability(
        "project.list_accessible",
        {
            "keyword": keyword,
            "status": status,
            "current": current,
            "size": size,
        },
    )


@MCP_SERVER.tool(
    name="requirement.get_detail",
    title="查询需求详情",
    description="查询项目内一条需求及其结构化需求点。",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
async def get_requirement_detail(
    project_id: int,
    requirement_id: int,
) -> dict[str, Any]:
    """在项目成员数据权限内读取需求详情。"""

    return await execute_mcp_capability(
        "requirement.get_detail",
        {"project_id": project_id, "requirement_id": requirement_id},
    )


@MCP_SERVER.tool(
    name="test_case.list",
    title="查询测试用例",
    description="分页查询项目内测试用例，可按模块、状态和来源筛选。",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
async def list_test_cases(
    project_id: int,
    keyword: str = "",
    module_id: int | None = None,
    status: TestCaseStatus | None = None,
    source: TestCaseSource | None = None,
    current: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """在项目成员数据权限内分页读取测试用例。"""

    return await execute_mcp_capability(
        "test_case.list",
        {
            "project_id": project_id,
            "keyword": keyword,
            "module_id": module_id,
            "status": status,
            "source": source,
            "current": current,
            "size": size,
        },
    )


# 挂载到 FastAPI 时，内部路径使用根路径，最终公开地址由外层 /api/mcp/ 决定。
MCP_HTTP_APP = MCP_SERVER.streamable_http_app()
