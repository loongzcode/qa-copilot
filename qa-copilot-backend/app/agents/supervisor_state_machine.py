"""Supervisor 运行和步骤的确定性状态流转规则。"""

from app.core.constants import SupervisorExecutionStepStatus, SupervisorRunStatus

_RUN_TRANSITIONS: dict[SupervisorRunStatus, frozenset[SupervisorRunStatus]] = {
    SupervisorRunStatus.PLANNING: frozenset(
        {
            SupervisorRunStatus.PLAN_REJECTED,
            SupervisorRunStatus.FAILED,
            SupervisorRunStatus.READY,
            SupervisorRunStatus.WAITING_APPROVAL,
            SupervisorRunStatus.CANCELLED,
        }
    ),
    SupervisorRunStatus.WAITING_APPROVAL: frozenset(
        {SupervisorRunStatus.READY, SupervisorRunStatus.FAILED, SupervisorRunStatus.CANCELLED}
    ),
    SupervisorRunStatus.READY: frozenset({SupervisorRunStatus.RUNNING, SupervisorRunStatus.CANCELLED}),
    SupervisorRunStatus.RUNNING: frozenset(
        {SupervisorRunStatus.SUCCEEDED, SupervisorRunStatus.FAILED, SupervisorRunStatus.CANCELLED}
    ),
    SupervisorRunStatus.PLAN_REJECTED: frozenset(),
    SupervisorRunStatus.SUCCEEDED: frozenset(),
    SupervisorRunStatus.FAILED: frozenset(),
    SupervisorRunStatus.CANCELLED: frozenset(),
}

_STEP_TRANSITIONS: dict[SupervisorExecutionStepStatus, frozenset[SupervisorExecutionStepStatus]] = {
    SupervisorExecutionStepStatus.PROPOSED: frozenset(
        {
            SupervisorExecutionStepStatus.REJECTED,
            SupervisorExecutionStepStatus.READY,
            SupervisorExecutionStepStatus.WAITING_APPROVAL,
            SupervisorExecutionStepStatus.CANCELLED,
        }
    ),
    SupervisorExecutionStepStatus.WAITING_APPROVAL: frozenset(
        {SupervisorExecutionStepStatus.READY, SupervisorExecutionStepStatus.CANCELLED}
    ),
    SupervisorExecutionStepStatus.READY: frozenset(
        {
            SupervisorExecutionStepStatus.RUNNING,
            SupervisorExecutionStepStatus.SKIPPED,
            SupervisorExecutionStepStatus.CANCELLED,
        }
    ),
    SupervisorExecutionStepStatus.RUNNING: frozenset(
        {
            SupervisorExecutionStepStatus.SUCCEEDED,
            SupervisorExecutionStepStatus.FAILED,
            SupervisorExecutionStepStatus.CANCELLED,
        }
    ),
    SupervisorExecutionStepStatus.REJECTED: frozenset(),
    SupervisorExecutionStepStatus.SUCCEEDED: frozenset(),
    SupervisorExecutionStepStatus.FAILED: frozenset(),
    SupervisorExecutionStepStatus.SKIPPED: frozenset(),
    SupervisorExecutionStepStatus.CANCELLED: frozenset(),
}


def can_transition_supervisor_run(current: SupervisorRunStatus, target: SupervisorRunStatus) -> bool:
    """判断 Supervisor 主任务能否从当前状态进入目标状态。

    功能：阻止已成功、失败或取消的任务被再次启动或覆盖。
    作用：Service 修改数据库前先调用；Repository 仍会用当前状态条件执行原子更新。
    为什么用它：状态规则集中成一张表比散落的 if/else 更容易审查和测试，也能明确显示所有合法路径。
    """
    return target in _RUN_TRANSITIONS[current]


def can_transition_supervisor_step(
    current: SupervisorExecutionStepStatus,
    target: SupervisorExecutionStepStatus,
) -> bool:
    """判断一个计划步骤能否进入目标状态。

    功能：保证步骤必须先就绪再执行，并且执行终态不可被覆盖。
    作用：保护人工审批和实际工具调用之间的状态边界。
    为什么用它：模型不能决定状态流转；普通 Python 枚举和映射提供可预测、可单测的控制规则。
    """
    return target in _STEP_TRANSITIONS[current]
