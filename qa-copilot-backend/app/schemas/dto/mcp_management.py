"""MCP 管理页面请求对象。"""

from typing import Any

from pydantic import Field

from app.schemas.camel_model import CamelModel


class McpToolCallDTO(CamelModel):
    """页面试调用一个白名单 MCP 工具时提交的参数。"""

    arguments: dict[str, Any] = Field(default_factory=dict)
