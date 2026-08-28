"""Supervisor Service 的上下文保护和步骤持久化映射测试。"""

import pytest
from app.agents.supervisor_capabilities import AgentCapabilityDefinition, AgentCapabilityRegistry
from app.agents.supervisor_plan_validator import validate_supervisor_plan
from app.core.constants import SupervisorExecutionStepStatus, ToolRisk
from app.core.permissions import Permission
from app.exceptions import BadRequestException
from app.schemas.dto.supervisor import SupervisorPlanDTO, SupervisorPlanStepDTO
from app.services.supervisor_service import SupervisorService


def _service(registry: AgentCapabilityRegistry) -> SupervisorService:
    """构造只用于纯方法测试的 Service，不访问这些占位 Repository。"""
    return SupervisorService(
        repository=None,  # type: ignore[arg-type]
        project_repository=None,  # type: ignore[arg-type]
        project_member_repository=None,  # type: ignore[arg-type]
        ai_model_repository=None,  # type: ignore[arg-type]
        prompt_template_repository=None,  # type: ignore[arg-type]
        outbox_repository=None,
        registry=registry,
        planning_graph=None,
    )


def test_business_context_rejects_plain_token() -> None:
    """用户不能把访问令牌写入会发送给模型并持久化的业务上下文。"""
    with pytest.raises(BadRequestException):
        SupervisorService._ensure_context_safe({"connection": {"access_token": "plain-token"}})


def test_high_risk_plan_maps_to_waiting_approval_step() -> None:
    """高风险能力即使计划合法，也只能保存为等待审批，不能直接变成 READY。"""
    registry = AgentCapabilityRegistry(
        (
            AgentCapabilityDefinition(
                code="mysql.sync",
                name="同步数据库结构",
                description="执行已预览的数据库结构变更。",
                risk_level=ToolRisk.HIGH,
                required_permission=Permission.TOOL_EXECUTE,
                read_only=False,
                supervisor_enabled=True,
                mcp_enabled=False,
                requires_human_approval=True,
                service_operation="ToolCenterService.execute_task",
            ),
        )
    )
    plan = SupervisorPlanDTO(
        goal="同步数据库结构",
        steps=[
            SupervisorPlanStepDTO(
                step_id="sync_schema",
                capability_code="mysql.sync",
                purpose="同步已确认的结构差异",
                arguments={"tool_task_id": 10},
            )
        ],
    )
    validation = validate_supervisor_plan(plan, {Permission.TOOL_EXECUTE}, registry=registry)

    steps = _service(registry)._build_step_entities(1, plan, validation)

    assert len(steps) == 1
    assert steps[0].status == SupervisorExecutionStepStatus.WAITING_APPROVAL.value
    assert steps[0].risk_level == ToolRisk.HIGH.value
    assert steps[0].requires_human_approval is True
