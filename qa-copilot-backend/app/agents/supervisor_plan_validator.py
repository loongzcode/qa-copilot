"""Supervisor 候选计划的确定性安全校验。"""

from __future__ import annotations

from collections.abc import Collection

from pydantic import ValidationError

from app.agents.supervisor_capabilities import SUPERVISOR_CAPABILITY_REGISTRY, AgentCapabilityRegistry
from app.core.constants import CapabilityInvocationSource, SupervisorStepDecision
from app.schemas.dto.supervisor import SupervisorPlanDTO
from app.schemas.vo.supervisor import SupervisorPlanValidationVO, SupervisorValidatedStepVO


def validate_supervisor_plan(
    plan: SupervisorPlanDTO,
    granted_permissions: Collection[str],
    source: CapabilityInvocationSource = CapabilityInvocationSource.SUPERVISOR,
    registry: AgentCapabilityRegistry = SUPERVISOR_CAPABILITY_REGISTRY,
) -> SupervisorPlanValidationVO:
    """校验模型提出的计划能否进入执行阶段。

    功能：检查步骤编号、前置依赖、能力白名单、调用来源、用户权限和人工审批要求。
    作用：位于模型规划与真实业务 Service 之间，是 Supervisor 和 MCP 都不能绕过的安全门。
    为什么用它：大语言模型输出具有不确定性，权限与流程边界必须由普通 Python 代码确定；
    同时要求依赖只能指向前面的步骤，可直接保证计划无环，不需要再运行复杂的图环检测。
    """
    permission_set = set(granted_permissions)
    seen_step_ids: set[str] = set()
    plan_issues: list[str] = []
    validated_steps: list[SupervisorValidatedStepVO] = []

    for step in plan.steps:
        step_issues: list[str] = []
        capability = registry.get(step.capability_code)

        if step.step_id in seen_step_ids:
            step_issues.append(f"步骤编号重复：{step.step_id}")

        unknown_dependencies = [dependency for dependency in step.depends_on if dependency not in seen_step_ids]
        if unknown_dependencies:
            step_issues.append("前置步骤必须已经出现在当前步骤之前：" + "、".join(unknown_dependencies))

        requires_human_approval = False
        if capability is None:
            step_issues.append(f"能力未登记：{step.capability_code}")
        else:
            source_enabled = (
                capability.supervisor_enabled
                if source == CapabilityInvocationSource.SUPERVISOR
                else capability.mcp_enabled
            )
            if not source_enabled:
                step_issues.append(f"能力不允许从 {source.value} 调用：{capability.code}")
            if "*" not in permission_set and capability.required_permission not in permission_set:
                step_issues.append(f"缺少权限：{capability.required_permission}")
            if capability.arguments_model is not None:
                try:
                    capability.arguments_model.model_validate(step.arguments)
                except ValidationError as exc:
                    first_error = exc.errors()[0]
                    location = ".".join(str(part) for part in first_error["loc"]) or "arguments"
                    step_issues.append(f"能力参数不合法（{location}）：{first_error['msg']}")
            requires_human_approval = capability.requires_human_approval

        if step_issues:
            decision = SupervisorStepDecision.REJECTED
        elif requires_human_approval:
            decision = SupervisorStepDecision.BLOCKED_APPROVAL
        else:
            decision = SupervisorStepDecision.READY

        validated_steps.append(
            SupervisorValidatedStepVO(
                step_id=step.step_id,
                capability_code=step.capability_code,
                decision=decision,
                requires_human_approval=requires_human_approval,
                issues=step_issues,
            )
        )
        plan_issues.extend(step_issues)
        seen_step_ids.add(step.step_id)

    valid = all(step.decision != SupervisorStepDecision.REJECTED for step in validated_steps)
    requires_human_approval = any(step.requires_human_approval for step in validated_steps)
    return SupervisorPlanValidationVO(
        valid=valid,
        executable_now=valid and not requires_human_approval,
        requires_human_approval=requires_human_approval,
        issues=plan_issues,
        steps=validated_steps,
    )
