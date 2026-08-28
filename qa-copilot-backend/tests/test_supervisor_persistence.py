"""Supervisor 持久化实体和状态机的边界测试。"""

from app.agents.supervisor_state_machine import can_transition_supervisor_run, can_transition_supervisor_step
from app.core.constants import SupervisorExecutionStepStatus, SupervisorRunStatus
from app.models import SupervisorPlanStep, SupervisorRun


def test_supervisor_models_have_database_comments_and_project_boundary() -> None:
    """主表和步骤表必须具有数据库注释，主表必须以 project_id 作为数据权限边界。"""
    assert SupervisorRun.__table__.comment
    assert SupervisorPlanStep.__table__.comment
    assert SupervisorRun.__table__.c.project_id.comment
    assert SupervisorPlanStep.__table__.c.arguments_snapshot.comment


def test_run_requires_planning_before_execution() -> None:
    """PLANNING 不能直接跳到 RUNNING，必须先完成计划校验并进入 READY。"""
    assert can_transition_supervisor_run(SupervisorRunStatus.PLANNING, SupervisorRunStatus.READY)
    assert not can_transition_supervisor_run(SupervisorRunStatus.PLANNING, SupervisorRunStatus.RUNNING)
    assert can_transition_supervisor_run(SupervisorRunStatus.READY, SupervisorRunStatus.RUNNING)


def test_terminal_run_cannot_be_restarted() -> None:
    """已成功运行不可再次启动，避免重复调用工具。"""
    assert not can_transition_supervisor_run(SupervisorRunStatus.SUCCEEDED, SupervisorRunStatus.RUNNING)


def test_approval_step_cannot_run_before_approval() -> None:
    """等待人工审批的步骤只能变为 READY 或取消，不能由 Agent 直接执行。"""
    assert not can_transition_supervisor_step(
        SupervisorExecutionStepStatus.WAITING_APPROVAL,
        SupervisorExecutionStepStatus.RUNNING,
    )
    assert can_transition_supervisor_step(
        SupervisorExecutionStepStatus.WAITING_APPROVAL,
        SupervisorExecutionStepStatus.READY,
    )


def test_successful_step_is_terminal() -> None:
    """成功步骤不能重新执行，确保消息重投时保持幂等。"""
    assert not can_transition_supervisor_step(
        SupervisorExecutionStepStatus.SUCCEEDED,
        SupervisorExecutionStepStatus.RUNNING,
    )


def test_proposed_step_can_be_cancelled_before_execution() -> None:
    """用户在规划阶段取消时，已经暂存但尚未就绪的步骤也必须能够收口。"""
    assert can_transition_supervisor_step(
        SupervisorExecutionStepStatus.PROPOSED,
        SupervisorExecutionStepStatus.CANCELLED,
    )
