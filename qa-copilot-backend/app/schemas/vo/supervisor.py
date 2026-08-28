"""Supervisor 计划、步骤和安全校验返回对象。"""

from datetime import datetime
from typing import Any

from app.core.constants import (
    CapabilityInvocationSource,
    SupervisorExecutionStepStatus,
    SupervisorRunStatus,
    SupervisorStepDecision,
    ToolRisk,
)
from app.schemas.camel_model import CamelModel


class SupervisorValidatedStepVO(CamelModel):
    """一个计划步骤的确定性校验结果。"""

    step_id: str
    capability_code: str
    decision: SupervisorStepDecision
    requires_human_approval: bool = False
    issues: list[str]


class SupervisorPlanValidationVO(CamelModel):
    """整个候选计划能否进入执行阶段的汇总结果。"""

    valid: bool
    executable_now: bool
    requires_human_approval: bool
    issues: list[str]
    steps: list[SupervisorValidatedStepVO]


class SupervisorPlanStepVO(CamelModel):
    """前端展示的一条 Supervisor 计划步骤及其安全状态。"""

    id: int
    step_no: int
    step_key: str
    capability_code: str
    purpose: str
    arguments_snapshot: dict[str, Any]
    depends_on: list[str]
    required_permission: str
    risk_level: ToolRisk
    decision: SupervisorStepDecision
    requires_human_approval: bool
    status: SupervisorExecutionStepStatus
    tool_task_id: int | None
    result_snapshot: dict[str, Any]
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    approval_decided_by: int | None
    approval_decision: str | None
    approval_comment: str | None
    approval_decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SupervisorRunVO(CamelModel):
    """Supervisor 运行列表使用的轻量信息。"""

    id: int
    project_id: int
    goal: str
    invocation_source: CapabilityInvocationSource
    status: SupervisorRunStatus
    current_step_no: int
    plan_version: int
    model_id: int | None
    requested_by: int | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    execution_heartbeat_at: datetime | None
    execution_recovery_count: int
    created_at: datetime
    updated_at: datetime


class SupervisorRunDetailVO(SupervisorRunVO):
    """Supervisor 运行详情，额外包含上下文快照、结果和全部步骤。"""

    permission_snapshot: list[str]
    context_snapshot: dict[str, Any]
    result_summary: dict[str, Any]
    steps: list[SupervisorPlanStepVO]
