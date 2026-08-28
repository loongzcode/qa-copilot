"""Supervisor 与 MCP 共用安全边界的单元测试。"""

from app.agents.supervisor_capabilities import AgentCapabilityDefinition, AgentCapabilityRegistry
from app.agents.supervisor_plan_validator import validate_supervisor_plan
from app.core.constants import CapabilityInvocationSource, SupervisorStepDecision, ToolRisk
from app.core.permissions import Permission
from app.schemas.dto.supervisor import SupervisorPlanDTO, SupervisorPlanStepDTO


def _plan(capability_code: str = "quality_delivery.get_status") -> SupervisorPlanDTO:
    """构造只有一个步骤的最小候选计划，方便各测试只改变一个安全条件。"""
    return SupervisorPlanDTO(
        goal="判断需求下一步应由谁处理",
        steps=[
            SupervisorPlanStepDTO(
                step_id="inspect_status",
                capability_code=capability_code,
                purpose="读取当前质量交付状态",
                arguments={"project_id": 8, "requirement_id": 1},
            )
        ],
    )


def test_valid_read_only_plan_is_ready() -> None:
    result = validate_supervisor_plan(_plan(), {Permission.REQUIREMENT_VIEW})

    assert result.valid is True
    assert result.executable_now is True
    assert result.steps[0].decision == SupervisorStepDecision.READY


def test_superuser_wildcard_satisfies_capability_permission() -> None:
    """超级管理员的通配符代表拥有全部能力权限，不能被误判成缺少具体权限码。"""
    result = validate_supervisor_plan(_plan(), {"*"})

    assert result.valid is True
    assert result.executable_now is True


def test_invalid_capability_arguments_are_rejected() -> None:
    """能力编码合法也不能跳过参数 Schema，例如项目 ID 必须是正整数。"""
    plan = _plan()
    plan.steps[0].arguments = {"project_id": 0, "requirement_id": 1}

    result = validate_supervisor_plan(plan, {Permission.REQUIREMENT_VIEW})

    assert result.valid is False
    assert "能力参数不合法" in result.issues[0]


def test_unknown_capability_is_rejected() -> None:
    result = validate_supervisor_plan(_plan("invented.delete_everything"), {Permission.REQUIREMENT_VIEW})

    assert result.valid is False
    assert result.executable_now is False
    assert "能力未登记" in result.issues[0]


def test_missing_permission_is_rejected() -> None:
    result = validate_supervisor_plan(_plan(), set())

    assert result.valid is False
    assert result.issues == [f"缺少权限：{Permission.REQUIREMENT_VIEW}"]


def test_dependency_must_reference_an_earlier_step() -> None:
    plan = _plan()
    plan.steps[0].depends_on = ["future_step"]

    result = validate_supervisor_plan(plan, {Permission.REQUIREMENT_VIEW})

    assert result.valid is False
    assert "前置步骤必须已经出现" in result.issues[0]


def test_high_risk_capability_cannot_skip_human_approval() -> None:
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

    result = validate_supervisor_plan(
        _plan("mysql.sync"),
        {Permission.TOOL_EXECUTE},
        registry=registry,
    )

    assert result.valid is True
    assert result.executable_now is False
    assert result.requires_human_approval is True
    assert result.steps[0].decision == SupervisorStepDecision.BLOCKED_APPROVAL


def test_mcp_cannot_call_internal_only_capability() -> None:
    registry = AgentCapabilityRegistry(
        (
            AgentCapabilityDefinition(
                code="internal.inspect",
                name="内部检查",
                description="只允许应用内部 Supervisor 调用。",
                risk_level=ToolRisk.LOW,
                required_permission=Permission.REQUIREMENT_VIEW,
                read_only=True,
                supervisor_enabled=True,
                mcp_enabled=False,
                requires_human_approval=False,
                service_operation="InternalService.inspect",
            ),
        )
    )

    result = validate_supervisor_plan(
        _plan("internal.inspect"),
        {Permission.REQUIREMENT_VIEW},
        source=CapabilityInvocationSource.MCP,
        registry=registry,
    )

    assert result.valid is False
    assert "不允许从 MCP 调用" in result.issues[0]
