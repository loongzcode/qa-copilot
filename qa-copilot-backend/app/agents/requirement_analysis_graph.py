"""需求拆解 LangGraph 的状态、运行依赖、节点和流程连接。

本模块只处理“调用模型 → 校验输出 → 按结果结束或重试”的 AI 工作流，不读取或
写入业务数据库。数据库事务、任务状态和需求点落库由外层执行 Service 负责。
"""
import json
from typing import Any, Literal, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, ValidationError

from app.agents.requirement_analysis_schemas import RequirementExtractionOutput
from app.core.constants import AIModelTaskType
from app.models import AIModel, PromptTemplate
from app.repositories.ai_model_repository import AIModelRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.utils.ai_client_util import generate_text_with_langchain


class RequirementAnalysisState(TypedDict, total=False):
    """定义需求分析 Graph 中所有节点共享的数据结构。

    功能：声明需求正文、模型原始输出、校验结果和重试信息等可用字段。
    作用：LangGraph 把每个节点返回的字典合并到 State，再把更新后的 State 传给
    下一个节点，从而让多个独立方法共同完成一次需求拆解。
    为什么用它：TypedDict 只约束字典字段，不会额外创建运行时对象，既符合
    LangGraph 的 State API，也能让 IDE 检查字段名和类型；total=False 允许节点
    分阶段补充字段，而不要求初始输入一次提供所有数据。
    """

    project_id: int
    requirement_id: int
    # 从关联知识文档读取出来的原始需求正文。
    requirement_text: str
    # AI 拆解并通过 Pydantic 校验的原子需求点。
    requirement_items: list[dict[str, Any]]
    # 根据已确认需求点召回的历史标准用例。
    retrieved_cases: list[dict[str, Any]]
    # 已有用例与需求点之间的 FULL/PARTIAL 覆盖关系。
    coverage_links: list[dict[str, Any]]
    # 没有覆盖或只被部分覆盖、需要补充生成的需求点。
    coverage_gaps: list[dict[str, Any]]
    # AI 生成并通过结构校验、质量检查和判重的草稿用例。
    generated_cases: list[dict[str, Any]]
    # 结构化输出校验失败原因，供有限次数修复或转人工处理。
    validation_errors: list[str]
    # 已经要求模型修复了几次
    retry_count: int
    # 模型本次返回的原始 JSON 字符串
    raw_output: str
    # 通过 RequirementExtractionOutput 校验后的结果.经过 Pydantic 校验后的可信对象。
    extraction_output: RequirementExtractionOutput | None
    # 当前文档真实存在的切片 ID 集合
    allowed_source_chunk_ids: list[int]
    # 上一次校验失败的原因，下一次调用模型时放入 Prompt。
    validation_feedback: str


class RequirementAnalysisContext(BaseModel):
    """保存需求拆解 Graph 各节点共同使用的运行依赖。

    功能：集中携带本次实际使用的模型、Prompt、Repository 和 AI 调用日志上下文。
    作用：Service 在启动 Graph 时创建 Context；节点通过 ``runtime.context`` 取得
    工具，不需要把数据库对象和模型配置塞入业务 State。
    为什么用它：State 适合保存可传递的业务数据，Context 适合保存不应被节点
    返回值覆盖的运行工具。这里继承 BaseModel 并允许任意类型，是为了满足当前
    LangGraph 的 Context 类型约束，同时保留 Repository、ORM 实体等 Python 对象。
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 调用统一 AI 工具并记录使用日志时需要。
    ai_model_repository: AIModelRepository

    # 本次需求拆解实际使用的模型。
    ai_model: AIModel

    # 本次需求拆解使用的 Prompt 模板。
    prompt_template: PromptTemplate

    # AI 调用日志所需的用户、项目和任务信息。
    usage_context: AIUsageContextDTO


async def extract_requirement_items(
        state: RequirementAnalysisState,
        runtime: Runtime[RequirementAnalysisContext],
) -> dict[str, object]:
    """调用大模型，把需求正文拆解为结构化 JSON 原文。

    功能：使用配置好的 Prompt 和模型，将需求正文、上次校验反馈以及目标 JSON
    Schema 发送给 AI，并把模型返回正文写入 ``raw_output``。
    作用：这是 Graph 的模型调用节点，接收初始 State 或校验失败后的 State；它的
    返回字典会由 LangGraph 合并到 State，随后交给校验节点处理。
    为什么用它：模型输出具有不确定性，因此这里只保留原始字符串，不直接当作
    可信业务对象。复用统一 LangChain 工具还能统一模型适配、Token 统计和调用日志；
    替代方案是直接调用服务商 SDK，但会造成不同模型的调用逻辑分散。
    """

    # PromptTemplate 是数据库配置；这里转换为 LangChain ChatPromptTemplate，
    # 才能用相同的变量字典同时渲染 system 和 human 消息。
    chat_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", runtime.context.prompt_template.system_prompt),
            ("human", runtime.context.prompt_template.user_prompt),
        ]
    )
    # 三个变量的职责：
    # - requirement_text：本次需要拆解的需求正文；
    # - validation_feedback：上次校验失败原因，第一次调用时为空字符串；
    # - output_schema：由 Pydantic 生成，告诉 AI 最终 JSON 的字段和类型约束。
    generation_result = await generate_text_with_langchain(
        repository=runtime.context.ai_model_repository,
        provider=runtime.context.ai_model.provider,
        model=runtime.context.ai_model,
        chat_prompt=chat_prompt,
        input_variables={
            "requirement_text": state["requirement_text"],
            "validation_feedback": state.get(
                "validation_feedback",
                "",
            ),
            "output_schema": json.dumps(
                RequirementExtractionOutput.model_json_schema(),
                ensure_ascii=False,
            ),
        },
        task_type=AIModelTaskType.REQUIREMENT_ANALYSIS.value,
        # 需求拆解需要模型尽快返回严格 JSON，而不是生成长篇分析过程。当前
        # deepseek-v4-flash 在 low 模式下曾把 8192 个输出 Token 全部用于推理，
        # 最终没有留下正文；这里只局部降到 minimal，不影响其他 AI 任务。
        reasoning_effort="minimal",
        usage_context=runtime.context.usage_context,
    )
    # 节点不直接修改传入的 state。LangGraph 会把下面的返回字典合并到当前
    # State，因此校验节点能够通过 state["raw_output"] 读取本次模型结果。
    return {
        "raw_output": generation_result.content,
    }


def validate_requirement_items(
        state: RequirementAnalysisState,
) -> dict[str, object]:
    """校验模型返回的需求点结构、父子关系和来源切片。

    功能：先用 Pydantic 把 ``raw_output`` 转换成结构化对象，再检查每条需求点
    引用的切片 ID 是否属于当前文档；失败时生成可反馈给模型的错误列表。
    作用：这是模型调用后的质量闸门。只有写入 ``extraction_output`` 的结果才能
    被外层 Service 保存；失败结果则通过 ``validation_feedback`` 驱动下一轮修复。
    为什么用它：Pydantic 适合确定性地校验 JSON、字段类型和父子关系，但它不
    知道数据库中哪些切片属于当前文档，所以还要用白名单做第二层业务校验。
    与完全依赖 Prompt 相比，程序校验能阻止模型格式漂移和伪造来源进入数据库。
    """

    # 每次模型重新生成后都要从空列表开始校验，不能继续沿用上一次的错误。
    validation_errors: list[str] = []
    # 原始字符串通过 Pydantic 校验后，才会得到可信的结构化对象。
    extraction_output: RequirementExtractionOutput | None = None

    try:
        extraction_output = (
            RequirementExtractionOutput.model_validate_json(
                state["raw_output"]
            )
        )
    except ValidationError as exc:
        # exc.errors() 返回每个字段的详细错误。例如 loc 为
        # ("items", 0, "title")，表示第一条需求点的 title 字段有问题。
        for error in exc.errors():
            location = ".".join(
                str(part) for part in error["loc"]
            )
            # 部分 JSON 整体格式错误没有具体字段位置，此时使用“整体输出”
            # 让反馈内容仍然容易理解。
            if not location:
                location = "整体输出"
            validation_errors.append(
                f"{location}：{error['msg']}"
            )

    # 只有 Pydantic 校验成功，extraction_output 才不是 None，才能继续
    # 遍历需求点。否则直接使用上面收集到的结构错误进入失败分支。
    if extraction_output is not None:
        # allowed_source_chunk_ids 来自当前需求文档真实存在的切片。
        # 转成 set 后可以使用集合减法快速找出 AI 编造的切片 ID。
        allowed_ids = set(
            state.get("allowed_source_chunk_ids", [])
        )

        for item in extraction_output.items:
            # 例如 AI 返回 {10, 99}，真实切片是 {10, 11, 12}，集合相减
            # 后得到 {99}，说明 99 不属于当前文档。
            invalid_ids = (
                    set(item.source_chunk_ids) - allowed_ids
            )

            if invalid_ids:
                validation_errors.append(
                    f"需求点 {item.local_id} 引用了不属于当前文档的切片："
                    f"{sorted(invalid_ids)}"
                )

    if validation_errors:
        # 把多条程序错误整理成人类和模型都能理解的文本。下一次调用
        # extract_requirement_items 时，会通过 {validation_feedback}
        # 把这些信息放入 Prompt，要求模型修正后重新输出完整 JSON。
        validation_feedback = (
                "上一次输出未通过校验，请修正以下问题并重新输出完整 JSON：\n"
                + "\n".join(
            f"- {error}" for error in validation_errors
        )
        )
        return {
            "extraction_output": None,
            "validation_errors": validation_errors,
            "validation_feedback": validation_feedback,
            # retry_count 记录已经失败的校验次数，路线方法会根据它决定
            # 是否允许再次调用模型。
            "retry_count": state.get("retry_count", 0) + 1,
        }

    # 没有任何错误，说明字段结构、父子关系和来源切片都可信。
    # 清空反馈，避免旧错误进入后续流程。
    return {
        "extraction_output": extraction_output,
        "validation_errors": [],
        "validation_feedback": "",
    }


RequirementExtractionRoute = Literal[
    "success",
    "retry",
    "failed",
]

MAX_REPAIR_RETRIES = 2


def route_after_validation(
        state: RequirementAnalysisState,
) -> RequirementExtractionRoute:
    """根据校验结果选择结束、重试或失败路线。

    功能：检查 ``extraction_output`` 和 ``retry_count``，返回 ``success``、
    ``retry`` 或 ``failed`` 三个固定路线名。
    作用：该方法由 ``add_conditional_edges`` 在校验节点结束后调用，只负责选择
    下一站，不执行模型、不修改 State；返回值会在路线映射表中转换为目标节点。
    为什么用它：把路线判断从节点中分离，可以保持校验方法只负责校验，也让
    重试上限集中且容易测试。先判断成功，能保证模型在最后一次机会修正成功时
    不会因为重试次数已高而被错误判定为失败。
    """

    if state.get("extraction_output") is not None:
        return "success"
    # retry_count 在每次校验失败后加 1。值为 1、2 时允许两次修复；第三次
    # 仍失败时值为 3，结束 Graph 并由外层 Service 抛出业务异常。
    retry_count = state.get("retry_count", 0)
    if retry_count <= MAX_REPAIR_RETRIES:
        return "retry"
    return "failed"


def build_requirement_extraction_graph():
    """注册需求拆解节点和线路，并编译为可执行 Graph。

    功能：创建 StateGraph，注册模型调用与结果校验节点，连接固定执行顺序和
    success/retry/failed 三条条件路线，最后返回编译结果。
    作用：模块加载时调用一次，生成可被 Celery 执行 Service 反复 ``ainvoke``
    的工作流对象；每次调用仍通过独立 State 和 Context 隔离任务数据。
    为什么用它：LangGraph 要求先声明完整拓扑再 compile。集中组装可以直接看出
    整个状态机，避免把跳转规则散落在 Service 中；普通 while 重试也能实现，
    但随着后续工作流节点增加会更难观察、扩展和调试。
    """

    # StateGraph 是尚未编译的流程构建器：State 描述流转数据，Context 描述
    # 节点运行时可以读取的工具。
    graph_builder = StateGraph(
        RequirementAnalysisState,
        context_schema=RequirementAnalysisContext,
    )
    # 注册“节点名 → Python 方法”的映射。注册只是在画流程图，不会立即执行。
    graph_builder.add_node(
        "extract_requirement_items",
        extract_requirement_items,
    )
    graph_builder.add_node(
        "validate_requirement_items",
        validate_requirement_items,
    )
    # add_edge(A, B) 不负责执行 A。它只记录：“A 已经执行完成后，接下来调度 B。”
    # Graph 开始后，首先执行模型调用节点。
    graph_builder.add_edge(
        START,
        "extract_requirement_items",
    )

    # 模型调用完成后，把更新后的 State 交给校验节点。
    graph_builder.add_edge(
        "extract_requirement_items",
        "validate_requirement_items",
    )
    graph_builder.add_conditional_edges(
        "validate_requirement_items",
        route_after_validation,
        {
            "success": END,
            "retry": "extract_requirement_items",
            "failed": END,
        },
    )
    # 所有节点和线路都添加完后，将流程图编译成可执行对象。compile 之后不再
    # 增加线路，外层只需要调用 ainvoke 并传入每次任务的数据。
    return graph_builder.compile()

# Graph 拓扑固定，因此在模块加载时只编译一次；任务之间不会共享业务 State，
# 每次 ainvoke 都会接收独立的初始 State 和 Context。
REQUIREMENT_EXTRACTION_GRAPH = (
    build_requirement_extraction_graph()
)

# 该顺序直接来自系统设计文档，后续组装 Graph 时不再临时决定流程。
REQUIREMENT_ANALYSIS_NODE_ORDER: tuple[str, ...] = (
    "load_requirement",
    "extract_requirement_items",
    "validate_requirement_items",
    "retrieve_standard_cases",
    "build_coverage_matrix",
    "identify_gaps",
    "generate_missing_cases",
    "quality_and_duplicate_check",
    "save_drafts",
)
