"""Supervisor 目标规划 LangGraph：模型规划、结构校验和有限修复。"""

from __future__ import annotations

import json
from typing import Literal, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, ValidationError

from app.agents.supervisor_capabilities import AgentCapabilityRegistry
from app.agents.supervisor_plan_validator import validate_supervisor_plan
from app.agents.supervisor_planning_schemas import SupervisorPlanningOutput
from app.core.constants import AIModelTaskType, CapabilityInvocationSource
from app.models import AIModel, PromptTemplate
from app.repositories.ai_model_repository import AIModelRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.schemas.dto.supervisor import SupervisorPlanDTO, SupervisorPlanStepDTO
from app.schemas.vo.supervisor import SupervisorPlanValidationVO
from app.utils.ai_client_util import generate_text_with_langchain

MAX_SUPERVISOR_PLAN_RETRIES = 1


class SupervisorPlanningState(TypedDict, total=False):
    """Supervisor 规划节点之间传递的业务状态。

    功能：保存原始目标、脱敏上下文、模型输出、可信计划和校验反馈。
    作用：LangGraph 会把每个节点返回的字典合并后传给下一节点。
    为什么用它：TypedDict 不创建额外运行时对象，适合 LangGraph 的增量字典状态；
    total=False 允许字段由不同节点逐步补齐。
    """

    goal: str
    business_context_json: str
    available_capabilities_json: str
    raw_output: str
    plan: SupervisorPlanDTO | None
    validation: SupervisorPlanValidationVO | None
    validation_errors: list[str]
    validation_feedback: str
    retry_count: int


class SupervisorPlanningContext(BaseModel):
    """规划节点共用但不写入 Graph State 的运行依赖。

    功能：携带模型、Prompt、能力目录、权限集合和 AI 调用日志上下文。
    作用：Service 创建一次 Context，节点从 ``runtime.context`` 读取稳定依赖。
    为什么用它：Repository、ORM 模型和能力目录不属于可序列化业务状态；放入 Context
    可以避免被节点返回值覆盖，也不会混入模型 Prompt 或最终任务快照。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ai_model_repository: AIModelRepository
    ai_model: AIModel
    prompt_template: PromptTemplate
    usage_context: AIUsageContextDTO
    registry: AgentCapabilityRegistry
    granted_permissions: frozenset[str]
    invocation_source: CapabilityInvocationSource


async def generate_supervisor_plan(
    state: SupervisorPlanningState,
    runtime: Runtime[SupervisorPlanningContext],
) -> dict[str, object]:
    """调用模型，把开放目标转换成候选能力步骤 JSON。

    功能：渲染目标、脱敏上下文、允许能力目录、输出 Schema 和修复反馈。
    作用：它是 Graph 中唯一调用大语言模型的节点，只生成候选计划，不调用任何工具。
    为什么用它：模型擅长把自然语言目标拆成步骤，但不适合决定权限；因此这里只保留
    原始输出，下一节点必须用 Pydantic、白名单和实时权限进行确定性校验。
    """
    chat_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", runtime.context.prompt_template.system_prompt),
            ("human", runtime.context.prompt_template.user_prompt),
        ]
    )
    result = await generate_text_with_langchain(
        repository=runtime.context.ai_model_repository,
        provider=runtime.context.ai_model.provider,
        model=runtime.context.ai_model,
        chat_prompt=chat_prompt,
        input_variables={
            "goal": state["goal"],
            "business_context_json": state["business_context_json"],
            "available_capabilities_json": state["available_capabilities_json"],
            "output_schema": json.dumps(SupervisorPlanningOutput.model_json_schema(), ensure_ascii=False),
            "validation_feedback": state.get("validation_feedback", ""),
        },
        task_type=AIModelTaskType.SUPERVISOR_PLANNING.value,
        reasoning_effort="minimal",
        usage_context=runtime.context.usage_context,
    )
    return {"raw_output": result.content}


def parse_and_validate_supervisor_plan(
    *,
    raw_output: str,
    goal: str,
    granted_permissions: frozenset[str],
    invocation_source: CapabilityInvocationSource,
    registry: AgentCapabilityRegistry,
) -> tuple[SupervisorPlanDTO | None, SupervisorPlanValidationVO | None, list[str]]:
    """把模型原文转换成可信计划并执行权限安全校验。

    功能：先用 Pydantic 解析 JSON，再调用共用计划校验器检查能力、依赖、来源和权限。
    作用：Graph 节点和单元测试共用该纯函数；返回的计划仍只是候选数据，不代表已执行。
    为什么用它：把纯校验从 LangGraph Runtime 中拆出后无需模型和数据库即可测试；
    同时保留两层校验，Pydantic 负责结构，计划校验器负责业务安全。
    """
    try:
        output = SupervisorPlanningOutput.model_validate_json(raw_output)
    except ValidationError as exc:
        errors = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"]) or "整体输出"
            errors.append(f"{location}：{error['msg']}")
        return None, None, errors

    plan = SupervisorPlanDTO(
        goal=goal,
        steps=[
            SupervisorPlanStepDTO(
                step_id=step.step_id,
                capability_code=step.capability_code,
                purpose=step.purpose,
                arguments=step.arguments,
                depends_on=step.depends_on,
            )
            for step in output.steps
        ],
    )
    validation = validate_supervisor_plan(
        plan,
        granted_permissions,
        source=invocation_source,
        registry=registry,
    )
    return plan, validation, list(validation.issues)


def validate_generated_supervisor_plan(
    state: SupervisorPlanningState,
    runtime: Runtime[SupervisorPlanningContext],
) -> dict[str, object]:
    """校验当前模型输出，并生成下一次模型修复可以理解的反馈。

    功能：调用纯校验函数，成功时保存可信计划；失败时累计次数和反馈。
    作用：这是模型输出与持久化 Service 之间的质量和权限闸门。
    为什么用它：模型可能返回错误 JSON、未知能力或无权限步骤；把错误反馈给模型进行一次
    有限修复可提高可用性，而严格重试上限可以防止无限循环和 Token 成本失控。
    """
    plan, validation, errors = parse_and_validate_supervisor_plan(
        raw_output=state.get("raw_output", ""),
        goal=state["goal"],
        granted_permissions=runtime.context.granted_permissions,
        invocation_source=runtime.context.invocation_source,
        registry=runtime.context.registry,
    )
    if errors:
        return {
            "plan": plan,
            "validation": validation,
            "validation_errors": errors,
            "validation_feedback": "请修正计划后重新输出完整 JSON：\n" + "\n".join(f"- {error}" for error in errors),
            "retry_count": state.get("retry_count", 0) + 1,
        }
    return {
        "plan": plan,
        "validation": validation,
        "validation_errors": [],
        "validation_feedback": "",
    }


def route_after_supervisor_validation(state: SupervisorPlanningState) -> Literal["success", "retry", "failed"]:
    """根据校验结果选择成功结束、重新规划一次或失败结束。"""
    validation = state.get("validation")
    if validation is not None and validation.valid:
        return "success"
    if state.get("retry_count", 0) <= MAX_SUPERVISOR_PLAN_RETRIES:
        return "retry"
    return "failed"


def build_supervisor_planning_graph():
    """注册并编译 Supervisor 规划 Graph。

    功能：形成“模型规划 → 确定性校验 → 成功或有限修复”的闭环。
    作用：Supervisor Service 复用编译结果，并在 Graph 完成后负责数据库事务。
    为什么用它：LangGraph 适合表达带条件和重试的流程；数据库提交留在 Service，
    避免模型节点重试时重复产生持久化副作用。
    """
    builder = StateGraph(SupervisorPlanningState, context_schema=SupervisorPlanningContext)
    builder.add_node("generate_supervisor_plan", generate_supervisor_plan)
    builder.add_node("validate_generated_supervisor_plan", validate_generated_supervisor_plan)
    builder.add_edge(START, "generate_supervisor_plan")
    builder.add_edge("generate_supervisor_plan", "validate_generated_supervisor_plan")
    builder.add_conditional_edges(
        "validate_generated_supervisor_plan",
        route_after_supervisor_validation,
        {
            "success": END,
            "retry": "generate_supervisor_plan",
            "failed": END,
        },
    )
    return builder.compile()


SUPERVISOR_PLANNING_GRAPH = build_supervisor_planning_graph()
