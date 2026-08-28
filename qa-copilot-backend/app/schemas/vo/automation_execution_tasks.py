from datetime import datetime
from typing import Any

from app.core.constants import AutomationExecutionStatus, AutomationStepStatus
from app.schemas.camel_model import CamelModel


class AutomationExecutionTaskVO(CamelModel):
    """向前端展示执行任务状态和不包含敏感信息的最小结论。"""

    id: int
    project_id: int
    definition_id: int
    definition_name: str
    definition_version: int
    environment_id: int
    environment_name: str
    status: AutomationExecutionStatus
    progress: int
    current_stage: str
    timeout_seconds: int
    celery_task_id: str | None
    result_summary: dict[str, Any]
    error_message: str | None
    requested_by: int | None
    requested_by_name: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AutomationExecutionStepResultVO(CamelModel):
    """报告中单个步骤的脱敏执行详情。"""

    id: int
    step_no: int
    name: str
    status: AutomationStepStatus
    method: str
    path: str
    status_code: int | None
    duration_ms: int | None
    request_summary: dict[str, Any]
    response_summary: dict[str, Any]
    assertions: list[dict[str, Any]]
    error_message: str | None


class AutomationExecutionReportVO(CamelModel):
    """一次任务的整体状态与按顺序排列的步骤结果。"""

    task: AutomationExecutionTaskVO
    steps: list[AutomationExecutionStepResultVO]
