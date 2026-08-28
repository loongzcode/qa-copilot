from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from app.core.constants import ToolRisk


class ToolPreview(BaseModel):
    summary: str
    changes: list[dict[str, Any]]
    warnings: list[str] = []
    requires_approval: bool = False


class ToolResult(BaseModel):
    success: bool
    message: str
    data: dict[str, Any] = {}
    artifact_keys: list[str] = []


class AgentTool(ABC):
    code: str
    name: str
    risk: ToolRisk

    @abstractmethod
    async def preview(self, params: BaseModel) -> ToolPreview:
        """只分析和预览，不修改外部系统。"""

    @abstractmethod
    async def execute(self, params: BaseModel) -> ToolResult:
        """审批通过后执行。"""

    async def rollback(self, task_id: int) -> ToolResult:
        """可选的回滚能力。"""
        raise NotImplementedError
