"""MCP 工具发现、权限过滤和只读调用业务服务。"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.agents.supervisor_capabilities import (
    SUPERVISOR_CAPABILITY_REGISTRY,
    AgentCapabilityRegistry,
    ProjectListArguments,
    QualityDeliveryStatusArguments,
    RequirementDetailArguments,
    TestCaseListArguments,
)
from app.core.config import settings
from app.core.deps import get_permission_codes
from app.exceptions import BadRequestException, ForbiddenException, InternalServerException
from app.models import User
from app.schemas.api_result import PageResult
from app.schemas.vo.mcp_management import McpServerInfoVO, McpToolCallResultVO, McpToolVO
from app.services.quality_delivery_service import QualityDeliveryService
from app.services.requirements_service import RequirementsService
from app.services.test_cases_service import TestCasesService
from app.services.test_projects_service import TestProjectsService


class McpManagementService:
    """统一执行管理页面和 MCP 协议入口允许使用的只读能力。

    功能：按当前用户过滤工具目录、校验工具参数和权限，并调用现有业务 Service。
    作用：页面试调用和远程 MCP 调用共享这一层，避免两种入口行为不一致。
    为什么用它：工具协议只负责传输，不应该直接访问 Repository；复用 Service 才能
    保留项目成员、需求存在性和测试用例可见性等既有业务规则。
    """

    def __init__(
        self,
        project_service: TestProjectsService,
        requirement_service: RequirementsService,
        test_case_service: TestCasesService,
        quality_delivery_service: QualityDeliveryService,
        *,
        registry: AgentCapabilityRegistry = SUPERVISOR_CAPABILITY_REGISTRY,
    ) -> None:
        self.project_service = project_service
        self.requirement_service = requirement_service
        self.test_case_service = test_case_service
        self.quality_delivery_service = quality_delivery_service
        self.registry = registry

    @staticmethod
    def _permissions(current_user: User) -> frozenset[str]:
        return frozenset(
            code for code in get_permission_codes(current_user) if code is not None
        )

    def get_server_info(self, current_user: User) -> McpServerInfoVO:
        """返回连接配置及当前用户具备业务权限的 MCP 工具。"""

        permissions = self._permissions(current_user)
        tools = [
            McpToolVO(
                code=capability.code,
                name=capability.name,
                description=capability.description,
                risk_level=capability.risk_level,
                required_permission=capability.required_permission,
                read_only=capability.read_only,
                input_schema=(
                    capability.arguments_model.model_json_schema()
                    if capability.arguments_model is not None
                    else {}
                ),
            )
            for capability in self.registry.list_for_mcp()
            if "*" in permissions or capability.required_permission in permissions
        ]
        return McpServerInfoVO(
            enabled=settings.mcp_enabled,
            endpoint=settings.mcp_resource_server_url,
            transport="Streamable HTTP",
            auth_scheme="Bearer access token",
            tools=tools,
        )

    async def call_tool(
        self,
        tool_code: str,
        arguments: dict[str, Any],
        current_user: User,
    ) -> McpToolCallResultVO:
        """重新校验只读白名单、实时权限和参数后执行一次工具调用。"""

        capability = self.registry.get(tool_code)
        if capability is None or not capability.mcp_enabled or not capability.read_only:
            raise BadRequestException(f"工具不存在或不允许从 MCP 调用：{tool_code}")
        permissions = self._permissions(current_user)
        if "*" not in permissions and capability.required_permission not in permissions:
            raise ForbiddenException(f"缺少操作权限：{capability.required_permission}")
        if capability.arguments_model is None:
            raise InternalServerException(f"MCP 工具没有配置参数模型：{tool_code}")
        try:
            payload = capability.arguments_model.model_validate(arguments)
        except ValidationError as exc:
            raise BadRequestException(f"MCP 工具参数校验失败：{exc}") from exc

        if isinstance(payload, QualityDeliveryStatusArguments):
            result = await self.quality_delivery_service.get_status(
                payload.project_id,
                payload.requirement_id,
                current_user,
            )
            data = result.model_dump(mode="json", by_alias=True)
        elif isinstance(payload, ProjectListArguments):
            records, total = await self.project_service.list_projects(
                current_user,
                payload.current,
                payload.size,
                payload.keyword,
                payload.status,
            )
            data = PageResult(
                current=payload.current,
                size=payload.size,
                total=total,
                records=records,
            ).model_dump(mode="json", by_alias=True)
        elif isinstance(payload, RequirementDetailArguments):
            result = await self.requirement_service.get_requirement_detail(
                payload.project_id,
                payload.requirement_id,
                current_user,
            )
            data = result.model_dump(mode="json", by_alias=True)
        elif isinstance(payload, TestCaseListArguments):
            records, total = await self.test_case_service.list_test_cases(
                payload.project_id,
                current_user,
                payload.keyword,
                payload.module_id,
                payload.status,
                payload.source,
                payload.current,
                payload.size,
            )
            data = PageResult(
                current=payload.current,
                size=payload.size,
                total=total,
                records=records,
            ).model_dump(mode="json", by_alias=True)
        else:
            raise InternalServerException(f"MCP 工具已登记但没有执行适配器：{tool_code}")

        return McpToolCallResultVO(tool_code=tool_code, result=data)
