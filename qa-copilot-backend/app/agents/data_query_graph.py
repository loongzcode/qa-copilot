"""自然语言生成只读 SQL 的 LangGraph 工作流。"""

import json
import re
from typing import Literal, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.constants import AIModelTaskType, DataSourceDatabaseType
from app.data_query.sql_security import SQLSafetyValidator
from app.models import AIModel, PromptTemplate
from app.repositories.ai_model_repository import AIModelRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.schemas.dto.data_query import GeneratedSQLPayload
from app.utils.ai_client_util import generate_text_with_langchain


class DataQueryGraphState(TypedDict, total=False):
    """节点共享的问题、模型输出、校验结果和有限重试状态。"""

    question: str
    raw_output: str
    generated_payload: GeneratedSQLPayload | None
    normalized_sql: str
    referenced_tables: list[str]
    validation_errors: list[str]
    validation_feedback: str
    retry_count: int
    max_retries: int


class DataQueryGraphContext(BaseModel):
    """不会被 State 覆盖的模型、Prompt、Schema 和安全策略。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ai_model_repository: AIModelRepository
    ai_model: AIModel
    prompt_template: PromptTemplate
    usage_context: AIUsageContextDTO
    database_type: DataSourceDatabaseType
    database_name: str
    schema_context: str
    allowed_tables: set[str]
    sensitive_columns: dict[str, set[str]]
    max_rows: int
    max_retries: int
    validator: SQLSafetyValidator


def _strip_json_fence(value: str) -> str:
    """兼容模型偶尔包裹的 Markdown JSON 代码块。"""

    match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", value, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else value.strip()


async def generate_sql(
    state: DataQueryGraphState,
    runtime: Runtime[DataQueryGraphContext],
) -> dict[str, object]:
    """让模型根据当前数据库方言和真实 Schema 生成结构化 SQL 草稿。"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", runtime.context.prompt_template.system_prompt),
            ("human", runtime.context.prompt_template.user_prompt),
        ]
    )
    result = await generate_text_with_langchain(
        repository=runtime.context.ai_model_repository,
        provider=runtime.context.ai_model.provider,
        model=runtime.context.ai_model,
        chat_prompt=prompt,
        input_variables={
            "database_type": runtime.context.database_type.value,
            "database_name": runtime.context.database_name,
            "schema_context": runtime.context.schema_context,
            "question": state["question"],
            "validation_feedback": state.get("validation_feedback", ""),
            "output_schema": json.dumps(GeneratedSQLPayload.model_json_schema(), ensure_ascii=False),
        },
        task_type=AIModelTaskType.DATA_QUERY.value,
        reasoning_effort="minimal",
        usage_context=runtime.context.usage_context,
    )
    return {"raw_output": result.content}


def validate_generated_sql(
    state: DataQueryGraphState,
    runtime: Runtime[DataQueryGraphContext],
) -> dict[str, object]:
    """使用 Pydantic 与 SQL 抽象语法树双重校验模型输出。"""

    errors: list[str] = []
    payload: GeneratedSQLPayload | None = None
    try:
        payload = GeneratedSQLPayload.model_validate_json(_strip_json_fence(state["raw_output"]))
    except ValidationError as exc:
        errors.extend(
            f"{'.'.join(str(part) for part in error['loc']) or '整体输出'}：{error['msg']}" for error in exc.errors()
        )

    validation_result = None
    if payload is not None:
        validation_result = runtime.context.validator.validate(
            sql=payload.sql,
            database_type=runtime.context.database_type,
            parameters=payload.parameters,
            allowed_tables=runtime.context.allowed_tables,
            sensitive_columns=runtime.context.sensitive_columns,
            max_rows=runtime.context.max_rows,
        )
        errors.extend(validation_result.errors)

    if errors:
        feedback = "上一次 SQL 未通过校验，请修正并重新输出完整 JSON：\n" + "\n".join(
            f"- {error}" for error in errors
        )
        return {
            "generated_payload": None,
            "normalized_sql": "",
            "referenced_tables": [],
            "validation_errors": errors,
            "validation_feedback": feedback,
            "retry_count": state.get("retry_count", 0) + 1,
        }
    assert payload is not None and validation_result is not None
    return {
        "generated_payload": payload,
        "normalized_sql": validation_result.normalized_sql,
        "referenced_tables": validation_result.referenced_tables,
        "validation_errors": [],
        "validation_feedback": "",
    }


DataQueryRoute = Literal["success", "retry", "failed"]


def route_after_validation(
    state: DataQueryGraphState,
) -> DataQueryRoute:
    """校验成功则结束，失败时在配置上限内重新生成。"""

    if state.get("generated_payload") is not None:
        return "success"
    if state.get("retry_count", 0) <= state.get("max_retries", 0):
        return "retry"
    return "failed"


def build_data_query_graph():
    """编译固定的“生成 → 校验 → 修复或结束”工作流。"""

    builder = StateGraph(DataQueryGraphState, context_schema=DataQueryGraphContext)
    builder.add_node("generate_sql", generate_sql)
    builder.add_node("validate_generated_sql", validate_generated_sql)
    builder.add_edge(START, "generate_sql")
    builder.add_edge("generate_sql", "validate_generated_sql")
    builder.add_conditional_edges(
        "validate_generated_sql",
        route_after_validation,
        {"success": END, "retry": "generate_sql", "failed": END},
    )
    return builder.compile()


DATA_QUERY_GRAPH = build_data_query_graph()
