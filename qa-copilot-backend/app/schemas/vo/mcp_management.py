"""MCP 管理页面响应对象。"""

from typing import Any

from app.core.constants import ToolRisk
from app.schemas.camel_model import CamelModel


class McpToolVO(CamelModel):
    """一个允许当前用户查看的 MCP 工具定义。"""

    code: str
    name: str
    description: str
    risk_level: ToolRisk
    required_permission: str
    read_only: bool
    input_schema: dict[str, Any]


class McpServerInfoVO(CamelModel):
    """MCP 连接信息和当前用户可发现的工具目录。"""

    enabled: bool
    endpoint: str
    transport: str
    auth_scheme: str
    tools: list[McpToolVO]


class McpToolCallResultVO(CamelModel):
    """页面内一次只读工具试调用的结构化结果。"""

    tool_code: str
    result: dict[str, Any]
