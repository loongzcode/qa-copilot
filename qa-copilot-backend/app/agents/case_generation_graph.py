"""缺失测试用例生成 LangGraph：模型生成、结构校验、质量判重和有限修复。"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Literal, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, ValidationError

from app.agents.case_generation_schemas import CaseGenerationOutput
from app.core.constants import AIModelTaskType
from app.models import AIModel, PromptTemplate
from app.repositories.ai_model_repository import AIModelRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.utils.ai_client_util import generate_text_with_langchain

MAX_CASE_GENERATION_RETRIES = 2


class CaseGenerationState(TypedDict, total=False):
    """缺失用例生成 Graph 各节点共享的数据。

    功能：保存缺口需求、历史参考用例、模型原文、可信结构和修复反馈。
    作用：节点只返回自己更新的字段，LangGraph 合并后交给下一个节点。
    为什么用它：TypedDict 既满足 LangGraph 的字典状态模型，又能让 IDE 发现字段
    拼写错误；total=False 允许状态随流程逐步补齐。
    """

    gaps_json: str
    reference_cases_json: str
    raw_output: str
    generation_output: CaseGenerationOutput | None
    validation_feedback: str
    validation_errors: list[str]
    retry_count: int
    allowed_requirement_item_ids: list[int]
    allowed_source_case_ids: list[int]
    allowed_source_knowledge_chunk_ids: list[int]
    existing_case_signatures: list[dict[str, object]]


class CaseGenerationContext(BaseModel):
    """Graph 节点共同使用、但不写入 State 的运行依赖。

    功能：携带模型、Prompt、AI 日志上下文和模型 Repository。
    作用：由 Worker 执行 Service 构造，模型节点通过 runtime.context 使用。
    为什么用它：运行工具不属于业务状态，分离后不会被节点返回值覆盖，也不会被
    序列化进任务快照。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ai_model_repository: AIModelRepository
    ai_model: AIModel
    prompt_template: PromptTemplate
    usage_context: AIUsageContextDTO


async def generate_missing_cases(
    state: CaseGenerationState,
    runtime: Runtime[CaseGenerationContext],
) -> dict[str, object]:
    """调用模型生成缺口用例 JSON 原文。

    功能：把缺口需求、历史参考、Schema 和上次校验反馈渲染进 Prompt。
    作用：作为首次生成和修复重试共同入口，输出 raw_output 给校验节点。
    为什么用它：保留原始字符串而不是直接信任模型对象，使后续确定性校验可以阻止
    格式漂移和伪造 ID；统一 AI 工具同时记录 Token、耗时和失败原因。
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
            "coverage_gaps_json": state["gaps_json"],
            "reference_cases_json": state["reference_cases_json"],
            "output_schema": json.dumps(
                CaseGenerationOutput.model_json_schema(),
                ensure_ascii=False,
            ),
            "validation_feedback": state.get("validation_feedback", ""),
        },
        task_type=AIModelTaskType.TEST_CASE_GENERATION.value,
        usage_context=runtime.context.usage_context,
        # 用例生成要求模型输出严格 JSON。这里优先把 Token 留给可落库正文，
        # 避免推理过程耗尽最大输出额度后只留下半截 JSON。
        reasoning_effort="minimal",
    )
    return {"raw_output": result.content}


def validate_generated_cases(state: CaseGenerationState) -> dict[str, object]:
    """校验模型 JSON、字段结构和所有业务 ID 白名单。

    功能：使用 Pydantic 解析，再检查覆盖需求点和参考用例 ID 都来自本次输入。
    作用：只有写入 generation_output 的结果才可进入质量检查和最终落库。
    为什么用它：Pydantic 能校验类型和步骤结构，但不知道数据库中哪些 ID 被允许；
    白名单补上业务边界，避免模型幻觉 ID 产生跨项目或错误外键。
    """
    errors: list[str] = []
    parsed: CaseGenerationOutput | None = None
    try:
        parsed = CaseGenerationOutput.model_validate_json(state.get("raw_output", ""))
    except ValidationError as exc:
        errors.append(f"JSON/Pydantic 校验失败：{exc}")

    if parsed is not None:
        allowed_requirement_ids = set(state.get("allowed_requirement_item_ids", []))
        allowed_source_case_ids = set(state.get("allowed_source_case_ids", []))
        allowed_source_knowledge_chunk_ids = set(
            state.get("allowed_source_knowledge_chunk_ids", [])
        )
        covered_requirement_ids: set[int] = set()
        for generated_case in parsed.cases:
            covered_requirement_ids.update(generated_case.requirement_item_ids)
            invalid_requirement_ids = (
                set(generated_case.requirement_item_ids) - allowed_requirement_ids
            )
            if invalid_requirement_ids:
                errors.append(
                    f"{generated_case.local_id} 引用了未允许的需求点："
                    f"{sorted(invalid_requirement_ids)}"
                )
            invalid_source_case_ids = (
                set(generated_case.source_case_ids) - allowed_source_case_ids
            )
            if invalid_source_case_ids:
                errors.append(
                    f"{generated_case.local_id} 引用了未提供的历史用例："
                    f"{sorted(invalid_source_case_ids)}"
                )
            invalid_chunk_ids = (
                set(generated_case.source_knowledge_chunk_ids)
                - allowed_source_knowledge_chunk_ids
            )
            if invalid_chunk_ids:
                errors.append(
                    f"{generated_case.local_id} 引用了未提供的标准用例知识切片："
                    f"{sorted(invalid_chunk_ids)}"
                )
        # 分批以后，每一批都必须真正覆盖这一批交给模型的所有缺口。
        # 否则模型只返回部分合法用例时，结构虽然正确，业务结果却不完整。
        missing_requirement_ids = allowed_requirement_ids - covered_requirement_ids
        if missing_requirement_ids:
            errors.append(
                "以下需求点没有生成测试用例："
                f"{sorted(missing_requirement_ids)}"
            )

    if errors:
        retry_count = state.get("retry_count", 0) + 1
        return {
            "generation_output": None,
            "validation_errors": errors,
            "validation_feedback": "\n".join(errors)[:6000],
            "retry_count": retry_count,
        }
    return {
        "generation_output": parsed,
        "validation_errors": [],
        "validation_feedback": "",
    }


def _normalize_signature(value: str) -> str:
    """去除大小写、空白和标点差异，供重复用例比较使用。"""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def quality_and_duplicate_check(state: CaseGenerationState) -> dict[str, object]:
    """检查生成批次内部重复以及与历史用例的高相似重复。

    功能：把标题、步骤和预期拼成签名，使用规范化精确匹配和 SequenceMatcher。
    作用：作为落库前最后一道质量闸门，重复时把具体问题反馈给模型修复。
    为什么用它：模型容易生成措辞不同但业务相同的用例；纯标题比较会漏判，直接用
    模型判重又增加不确定性和费用，因此先采用可解释的确定性阈值。数据量扩大后，
    可将这一节点替换为向量召回 + Cross-Encoder 判重。
    """
    output = state.get("generation_output")
    if output is None:
        return {}
    errors: list[str] = []
    existing_signatures = state.get("existing_case_signatures", [])
    accepted_signatures: list[tuple[str, str]] = []
    for generated_case in output.cases:
        signature_text = " ".join(
            [
                generated_case.title,
                generated_case.preconditions,
                generated_case.expected_summary,
                *[step.action for step in generated_case.steps],
                *[step.expected_result for step in generated_case.steps],
            ]
        )
        normalized = _normalize_signature(signature_text)
        if not normalized:
            errors.append(f"{generated_case.local_id} 没有可用于判重的有效文本")
            continue
        for other_local_id, other_signature in accepted_signatures:
            similarity = SequenceMatcher(None, normalized, other_signature).ratio()
            if similarity >= 0.88:
                errors.append(
                    f"{generated_case.local_id} 与本批次 {other_local_id} 重复度 "
                    f"{similarity:.2f}"
                )
                break
        for existing in existing_signatures:
            existing_signature = _normalize_signature(str(existing.get("signature", "")))
            if not existing_signature:
                continue
            similarity = SequenceMatcher(None, normalized, existing_signature).ratio()
            if similarity >= 0.88:
                errors.append(
                    f"{generated_case.local_id} 与已有用例 "
                    f"{existing.get('case_id')} 重复度 {similarity:.2f}"
                )
                break
        accepted_signatures.append((generated_case.local_id, normalized))

    if errors:
        retry_count = state.get("retry_count", 0) + 1
        return {
            "generation_output": None,
            "validation_errors": errors,
            "validation_feedback": "请重新生成并消除下列重复：\n" + "\n".join(errors)[:6000],
            "retry_count": retry_count,
        }
    return {"validation_errors": [], "validation_feedback": ""}


def route_after_validation(
    state: CaseGenerationState,
) -> Literal["quality", "retry", "failed"]:
    """根据结构校验结果决定进入质量检查、重试或失败结束。"""
    if state.get("generation_output") is not None:
        return "quality"
    if state.get("retry_count", 0) <= MAX_CASE_GENERATION_RETRIES:
        return "retry"
    return "failed"


def route_after_quality(
    state: CaseGenerationState,
) -> Literal["success", "retry", "failed"]:
    """根据质量判重结果决定成功结束或重新生成。"""
    if state.get("generation_output") is not None:
        return "success"
    if state.get("retry_count", 0) <= MAX_CASE_GENERATION_RETRIES:
        return "retry"
    return "failed"


def build_case_generation_graph():
    """注册节点、连接条件边并编译可执行缺失用例生成 Graph。

    功能：形成“生成 → 结构校验 → 质量判重 → 成功/重试/失败”的闭环。
    作用：编译结果由 Worker 复用，单次任务只提供 State 和 Context。
    为什么用它：显式图结构比一个超长 Service 方法更容易观察每个阶段、增加重试和
    替换节点；有限循环避免模型格式错误造成无限调用和成本失控。
    """
    builder = StateGraph(
        CaseGenerationState,
        context_schema=CaseGenerationContext,
    )
    builder.add_node("generate_missing_cases", generate_missing_cases)
    builder.add_node("validate_generated_cases", validate_generated_cases)
    builder.add_node("quality_and_duplicate_check", quality_and_duplicate_check)
    builder.add_edge(START, "generate_missing_cases")
    builder.add_edge("generate_missing_cases", "validate_generated_cases")
    builder.add_conditional_edges(
        "validate_generated_cases",
        route_after_validation,
        {
            "quality": "quality_and_duplicate_check",
            "retry": "generate_missing_cases",
            "failed": END,
        },
    )
    builder.add_conditional_edges(
        "quality_and_duplicate_check",
        route_after_quality,
        {
            "success": END,
            "retry": "generate_missing_cases",
            "failed": END,
        },
    )
    return builder.compile()


CASE_GENERATION_GRAPH = build_case_generation_graph()
