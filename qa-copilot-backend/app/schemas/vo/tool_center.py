"""测试工具中心返回前端的脱敏视图。"""

from datetime import datetime
from typing import Any

from app.core.constants import FileTemplateFormat, ToolConnectionType, ToolRisk, ToolTaskStatus, ToolTaskType
from app.schemas.camel_model import CamelModel
from pydantic import Field


class ToolDefinitionVO(CamelModel):
    id: int
    code: str
    name: str
    description: str
    risk_level: ToolRisk
    required_permission: str
    enabled: bool


class ExternalConnectionVO(CamelModel):
    id: int
    project_id: int
    name: str
    connection_type: ToolConnectionType
    config: dict[str, Any]
    credentials_configured: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime


class FileTemplateVO(CamelModel):
    id: int
    project_id: int
    name: str
    file_format: FileTemplateFormat
    encoding: str
    delimiter: str | None
    fields: list[dict[str, Any]]
    header_config: dict[str, Any]
    trailer_config: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AIFileRecordsPreviewVO(CamelModel):
    """AI 合成记录及确定性模板校验结果。"""

    records: list[dict[str, Any]]
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    model_id: int
    input_tokens: int = 0
    output_tokens: int = 0


class ToolApprovalVO(CamelModel):
    id: int
    requester_id: int | None
    approver_id: int | None
    decision: str
    comment: str
    preview_hash: str
    created_at: datetime


class ToolLogVO(CamelModel):
    id: int
    stage: str
    level: str
    message: str
    details: dict[str, Any]
    created_at: datetime


class ToolArtifactVO(CamelModel):
    id: int
    artifact_type: str
    name: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class ToolTaskVO(CamelModel):
    id: int
    project_id: int
    tool_id: int
    tool_code: str
    tool_name: str
    task_type: ToolTaskType
    title: str
    risk_level: ToolRisk
    status: ToolTaskStatus
    requested_by: int | None
    input_data: dict[str, Any]
    preview_data: dict[str, Any] | None
    preview_hash: str | None
    result_data: dict[str, Any] | None
    rollback_data: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    approvals: list[ToolApprovalVO] = Field(default_factory=list)
    logs: list[ToolLogVO] = Field(default_factory=list)
    artifacts: list[ToolArtifactVO] = Field(default_factory=list)
