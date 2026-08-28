import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from app.core.constants import (
    KNOWLEDGE_EMBEDDING_DIMENSIONS,
    AIProviderType,
    AIUsageStatus,
)
from app.core.metrics import record_ai_model_call
from app.core.security import decrypt_secret
from app.exceptions import BadRequestException
from app.exceptions.errors import describe_exception
from app.models import AIModel, AIProvider
from app.repositories.ai_model_repository import AIModelRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO, AIUsageLogsCreateDTO

# 模型 SDK 的异常文本有时会带出请求头或配置值。调用日志只需要错误原因，
# 不应该保存 API Key、Token、密码等秘密，因此在写数据库前统一替换为 ***。
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r'''(?ix)
    (?P<prefix>
        ["']?
        (?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password)
        ["']?\s*[:=]\s*
    )
    (?P<value>"[^"]*"|'[^']*'|[^\s,;}\]]+)
    '''
)
_AUTHORIZATION_PATTERN = re.compile(
    r'''(?ix)
    (?P<prefix>["']?authorization["']?\s*[:=]\s*)
    (?P<value>
        "[^"]*"
        |'[^']*'
        |Bearer\s+[A-Za-z0-9._~+/=-]+
        |[^\s,;}\]]+
    )
    '''
)
_BEARER_TOKEN_PATTERN = re.compile(
    r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+"
)


@dataclass(slots=True)
class AIGenerationResult:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0


@dataclass(slots=True)
class AITextDelta:
    """流式生成过程中模型新返回的一小段文字。"""

    content: str


@dataclass(slots=True)
class AIEmbeddingResult:
    """Embedding 调用结果，向量可供后续知识库索引流程复用。"""

    vector: list[float]
    input_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0


@dataclass(slots=True)
class AIEmbeddingBatchResult:
    """一次批量 Embedding 调用的结果。"""

    vectors: list[list[float]]
    input_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0


@dataclass(slots=True)
class AIRerankItem:
    """Rerank 返回的一条排序结果。"""

    # 对应请求 documents 列表中的原始位置。
    index: int

    # 用户问题与该候选文档的相关性，越大越相关。
    relevance_score: float


@dataclass(slots=True)
class AIRerankResult:
    """一次 Rerank 模型调用的完整结果。"""

    results: list[AIRerankItem]
    total_tokens: int = 0
    latency_ms: int = 0


def _create_openai_client(provider: AIProvider) -> AsyncOpenAI:
    """根据服务商配置创建统一的异步 OpenAI 客户端。"""

    return AsyncOpenAI(
        api_key=decrypt_secret(provider.encrypted_api_key),
        base_url=provider.base_url or None,
        default_headers=provider.custom_headers or None,
        timeout=provider.timeout_seconds,
        max_retries=provider.max_retries,
    )


def _read_usage(usage: object | None) -> tuple[int, int, int]:
    """兼容 Responses 与 Chat Completions 两种 usage 字段。"""

    if usage is None:
        return 0, 0, 0
    input_tokens = int(getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0)) or 0)
    output_tokens = int(
        getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0)) or 0
    )
    total_tokens = int(getattr(usage, "total_tokens", input_tokens + output_tokens) or 0)
    return input_tokens, output_tokens, total_tokens


def _sanitize_usage_error(error_message: str | None) -> str | None:
    """脱敏并截断适合写入 AI 调用日志的错误摘要。"""

    if error_message is None:
        return None

    # Authorization 可能写成 ``Bearer xxx``，因此先整体替换授权字段；
    # 再处理没有 Authorization 字段名、单独出现在错误文本中的 Bearer。
    sanitized = _AUTHORIZATION_PATTERN.sub(
        lambda match: f"{match.group('prefix')}***",
        error_message,
    )
    sanitized = _BEARER_TOKEN_PATTERN.sub(r"\1***", sanitized)
    sanitized = _SENSITIVE_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group('prefix')}***",
        sanitized,
    )
    # DTO 和数据库错误摘要只保留前 2000 个字符，避免异常响应无限膨胀。
    return sanitized[:2000]


async def _record_ai_usage(
    repository: AIModelRepository,
    provider: AIProvider,
    model: AIModel,
    task_type: str,
    status: AIUsageStatus,
    *,
    context: AIUsageContextDTO | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    latency_ms: int = 0,
    error_message: str | None = None,
) -> None:
    """把模型配置、业务上下文和调用结果组合成一条可审计日志。

    上层生成工具只负责提供本次调用的状态、Token 和耗时；本方法统一补齐
    服务商/模型名称快照、用户/项目/请求/任务标识，并在写库前脱敏错误。
    """

    # 连接测试以外的系统任务可能没有用户或项目。使用空上下文可以让调用
    # 日志照常落库，而不是要求所有调用方重复判断每个可选字段。
    if context is None:
        context = AIUsageContextDTO()

    # provider/model 对象在真正调用模型前已经完成查询，因此名称快照直接
    # 从当前对象取得，不需要 Repository 再查询一次数据库。
    payload = AIUsageLogsCreateDTO(
        provider_id = provider.id,
        provider_name= provider.name,
        model_id=model.id,
        model_name=model.name,
        request_id=context.request_id,
        user_id=context.user_id,
        project_id=context.project_id,
        task_id=context.task_id,
        retrieval_hit_count=context.retrieval_hit_count,
        task_type=task_type,
        status=status,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        error_message=_sanitize_usage_error(error_message),
    )
    # Repository 只负责将已经完整、已校验的 DTO 映射成实体并提交。
    await repository.record_usage(payload)
    # 审计日志成功落库后再增加监控计数。这样数据库记录与 Prometheus 指标对同一次
    # 调用使用相同的成功/失败口径；监控本身不保存 Prompt 或模型回答正文。
    record_ai_model_call(
        task_type=task_type,
        status=status.value,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

async def generate_text(
        repository: AIModelRepository,
        provider: AIProvider,
        model: AIModel,
        system_prompt: str,
        user_prompt: str,
        task_type: str,
        usage_context: AIUsageContextDTO | None = None,
) -> AIGenerationResult:
    """统一调用 AI，并记录成功或失败的用量日志。"""

    started_at = time.perf_counter()
    client = _create_openai_client(provider)

    try:
        if provider.provider_type == "openai_responses":
            request_options: dict = {
                "model": model.model_id,
                "instructions": system_prompt,
                "input": user_prompt,
                "max_output_tokens": model.max_output_tokens,
            }
            if model.reasoning_effort:
                request_options["reasoning"] = {"effort": model.reasoning_effort}
            response = await client.responses.create(**request_options)
            content = response.output_text
            usage = response.usage
        else:
            # 大部分国内服务商目前兼容 Chat Completions，而不完全兼容 Responses API。
            response = await client.chat.completions.create(
                model=model.model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=model.max_output_tokens,
            )
            content = response.choices[0].message.content or ""
            usage = response.usage

        input_tokens, output_tokens, total_tokens = _read_usage(usage)
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        await _record_ai_usage(
            repository,
            provider,
            model,
            task_type,
            AIUsageStatus.SUCCESS,
            context=usage_context,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
        return AIGenerationResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        error_message = describe_exception(exc)
        await _record_ai_usage(
            repository,
            provider,
            model,
            task_type,
            AIUsageStatus.FAILED,
            context=usage_context,
            latency_ms=latency_ms,
            error_message=error_message,
        )
        raise


async def generate_embedding(
        repository: AIModelRepository,
        provider: AIProvider,
        model: AIModel,
        input_text: str,
        task_type: str,
        usage_context: AIUsageContextDTO | None = None,
) -> AIEmbeddingResult:
    """单文本 Embedding 兼容入口，内部复用批量实现。"""

    result = await generate_embeddings(
        repository=repository,
        provider=provider,
        model=model,
        input_texts=[input_text],
        task_type=task_type,
        usage_context=usage_context
    )
    return AIEmbeddingResult(
        vector=result.vectors[0],
        input_tokens=result.input_tokens,
        total_tokens=result.total_tokens,
        latency_ms=result.latency_ms,
    )


async def generate_embeddings(
        repository: AIModelRepository,
        provider: AIProvider,
        model: AIModel,
        input_texts: list[str],
        task_type: str,
        usage_context: AIUsageContextDTO | None = None,
) -> AIEmbeddingBatchResult:
    """批量调用 OpenAI 兼容 Embeddings API，并记录一次模型用量。"""

    if not input_texts:
        raise ValueError("Embedding 输入不能为空")

    started_at = time.perf_counter()
    client = _create_openai_client(provider)

    try:
        response = await client.embeddings.create(
            model=model.model_id,
            input=input_texts,
            dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
        )
        if len(response.data) != len(input_texts):
            raise RuntimeError("Embedding 服务返回的向量数量与输入数量不一致")

        ordered_data = sorted(response.data, key=lambda item: item.index)
        vectors = [
            [float(value) for value in item.embedding]
            for item in ordered_data
        ]
        if any(
            len(vector) != KNOWLEDGE_EMBEDDING_DIMENSIONS
            for vector in vectors
        ):
            raise RuntimeError(
                "Embedding 服务返回的向量维度不是 "
                f"{KNOWLEDGE_EMBEDDING_DIMENSIONS}"
            )
        input_tokens, _, total_tokens = _read_usage(response.usage)
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        await _record_ai_usage(
            repository,
            provider,
            model,
            task_type,
            AIUsageStatus.SUCCESS,
            context=usage_context,
            input_tokens=input_tokens,
            output_tokens=0,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
        return AIEmbeddingBatchResult(
            vectors=vectors,
            input_tokens=input_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        error_message = describe_exception(exc)
        await _record_ai_usage(
            repository,
            provider,
            model,
            task_type,
            AIUsageStatus.FAILED,
            context=usage_context,
            latency_ms=latency_ms,
            error_message = error_message
        )
        raise


async def rerank_documents(
        repository: AIModelRepository,
        provider: AIProvider,
        model: AIModel,
        query: str,
        documents: list[str],
        top_n: int,
        task_type: str,
        usage_context: AIUsageContextDTO | None = None,
) -> AIRerankResult:
    """调用文本 Rerank 接口，对候选文档进行精排并记录用量。"""
    # 校验 query 去空格后不为空
    # 校验 documents 不为空
    # 校验 top_n 大于 0
    # 校验 provider.base_url 已配置
    query = query.strip()
    if not query:
        raise ValueError("Rerank查询文本不能为空")
    if not documents:
        raise ValueError("Rerank候选文档不能为空")

    if top_n <= 0:
        raise ValueError("Rerank返回数量必须大于0")

    if not provider.base_url:
        raise ValueError("Rerank服务商地址未配置")
    # 记录开始时间
    started_at = time.perf_counter()
    try:
        # 解密 API Key
        # 如果密钥为空就报错
        api_key = decrypt_secret(provider.encrypted_api_key)
        if not api_key:
            raise ValueError("服务商密钥不允许为空")
        # 从 custom_headers 复制请求头
        # 写入 Authorization
        # 写入 Content-Type
        headers = dict(provider.custom_headers or {})
        headers["Authorization"] = (
            f"Bearer {api_key}"
        )
        headers["Content-Type"] = "application/json"
        # 组装请求体：
        # model
        # query
        # documents
        # top_n，不能超过 documents 数量
        # instruct，使用问答检索指令
        request_body = {
            "model": model.model_id,
            "query": query,
            "documents": documents,
            "top_n": min(top_n, len(documents)),
            "instruct": (
                "Given a web search query, retrieve relevant "
                "passages that answer the query."
            ),
        }
        # 创建支持重试的异步 HTTP Transport
        # 创建 AsyncClient
        # POST 请求 provider.base_url
        transport = httpx.AsyncHTTPTransport(
            retries=provider.max_retries,
        )

        async with httpx.AsyncClient(
                timeout=provider.timeout_seconds,
                transport=transport,
        ) as client:
            response = await client.post(
                provider.base_url,
                headers=headers,
                json=request_body,
            )
        # 如果 HTTP 状态失败
        # 抛出包含状态码和响应正文的异常
        if response.is_error:
            raise RuntimeError(
                f"Rerank调用失败：HTTP {response.status_code}，"
                f"{response.text[:2000]}"
            )
        # response.json() 取得响应字典
        # 从字典读取 results
        # results 必须是 list
        response_data = response.json()
        raw_results = response_data.get("results")
        if not isinstance(raw_results, list):
            raise RuntimeError("Rerank服务返回的results格式错误")
        # 创建 AIRerankItem 列表
        # 创建保存已出现 index 的集合
        rerank_items: list[AIRerankItem] = []
        seen_indexes: set[int] = set()
        # 遍历响应中的每条结果
        # 读取 index
        # 读取 relevance_score
        # 校验 index 在 documents 范围内
        # 校验 index 没有重复
        # 转换成 AIRerankItem 并加入列表
        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                raise RuntimeError("Rerank结果项格式错误")
            try:
                index = int(raw_result["index"])
                relevance_score = float(raw_result["relevance_score"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    "Rerank结果缺少合法的index或relevance_score"
                ) from exc
            if index < 0 or index >= len(documents):
                raise RuntimeError(
                    f"Rerank结果下标越界：{index}"
                )
            if index in seen_indexes:
                raise RuntimeError(
                    f"Rerank结果下标重复：{index}"
                )

            seen_indexes.add(index)
            rerank_items.append(
                AIRerankItem(
                    index=index,
                    relevance_score=relevance_score,
                )
            )

        # 按 relevance_score 从高到低排序
        rerank_items.sort(
            key=lambda item: item.relevance_score,
            reverse=True,
        )
        # 从 usage.total_tokens 读取 Token 用量
        usage = response_data.get("usage")

        if isinstance(usage, dict):
            total_tokens = int(
                usage.get("total_tokens", 0) or 0
            )
        else:
            total_tokens = 0

        # 计算耗时
        latency_ms = int(
            (time.perf_counter() - started_at) * 1000
        )
        # 写入成功用量日志
        await _record_ai_usage(
            repository,
            provider,
            model,
            task_type,
            AIUsageStatus.SUCCESS,
            context=usage_context,
            input_tokens=total_tokens,
            output_tokens=0,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
        # 返回 AIRerankResult
        return AIRerankResult(
            results=rerank_items,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        # 计算失败耗时
        latency_ms = int(
            (time.perf_counter() - started_at) * 1000
        )
        # 提取错误摘要
        error_message = describe_exception(exc)
        # 写入失败用量日志
        await _record_ai_usage(
            repository=repository,
            provider=provider,
            model=model,
            task_type=task_type,
            status=AIUsageStatus.FAILED,
            latency_ms=latency_ms,
            context=usage_context,
            error_message=error_message
        )
        # 继续抛出原异常
        raise


def create_langchain_chat_model(
        provider: AIProvider,
        model: AIModel,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
) -> ChatOpenAI:
    """根据数据库配置创建统一的 LangChain 聊天模型。

    功能：把服务商、模型、输出上限和可选的任务级推理强度转换成 ChatOpenAI。
    作用：知识问答、需求分析等业务统一通过这里创建客户端，避免各模块重复处理
    密钥解密、超时、重试和 Responses API 适配。
    为什么用它：大多数任务沿用模型表中的全局配置；少数结构化任务可以传入
    ``reasoning_effort`` 做局部覆盖，避免为了一个任务修改所有 AI 调用的配置。
    """
    api_key = decrypt_secret(provider.encrypted_api_key)

    if not api_key:
        raise BadRequestException("AI 服务商密钥未配置")
    if max_output_tokens is None:
        max_completion_tokens = model.max_output_tokens
    else:
        max_completion_tokens =  min(max_output_tokens , model.max_output_tokens)
    # 没有传任务级覆盖值时保持原行为，继续使用管理员配置的全局推理强度。
    effective_reasoning_effort = (
        model.reasoning_effort
        if reasoning_effort is None
        else reasoning_effort
    )
    return ChatOpenAI(
        model=model.model_id,
        api_key=api_key,
        stream_usage=True,
        base_url=provider.base_url or None,
        default_headers=provider.custom_headers or None,
        timeout=provider.timeout_seconds,
        max_retries=provider.max_retries,
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=effective_reasoning_effort,
        use_responses_api=(
                provider.provider_type
                == AIProviderType.OPENAI_RESPONSES.value
        ),
    )


async def generate_text_with_langchain(
        repository: AIModelRepository,
        provider: AIProvider,
        model: AIModel,
        chat_prompt: ChatPromptTemplate,
        input_variables: dict[str, object],
        task_type: str,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        usage_context: AIUsageContextDTO | None = None,
) -> AIGenerationResult:
    started_at = time.perf_counter()
    # 这些变量必须在 try 外初始化。这样即使后续发现正文为空或抛出异常，
    # except 仍然能把服务商已经返回的实际 Token 用量写入失败日志。
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    reasoning_tokens = 0
    completion_reason = "未知"
    try:
        langchain_model = create_langchain_chat_model(
            provider=provider,
            model=model,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
        )
        # 先让 chat_prompt 渲染变量，再把生成的消息交给 langchain_model  | 表示顺序管道
        chain = chat_prompt | langchain_model
        ai_message = await chain.ainvoke(input_variables)

        # 必须先读取用量和结束原因，再判断正文是否为空。部分推理模型可能已经
        # 消耗完输出额度，却只返回推理 Token、没有生成最终正文；如果先抛错，
        # 失败日志里的 Token 就会全部变成 0，无法判断真正原因。
        usage = ai_message.usage_metadata or {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
        output_token_details = usage.get("output_token_details") or {}
        if isinstance(output_token_details, dict):
            reasoning_tokens = int(output_token_details.get("reasoning", 0) or 0)

        response_metadata = ai_message.response_metadata or {}
        completion_reason = str(
            response_metadata.get("finish_reason")
            or response_metadata.get("stop_reason")
            or response_metadata.get("status")
            or "未知"
        )

        content = ai_message.text.strip()
        if not content:
            raise RuntimeError(
                "AI 模型未返回可用正文"
                f"（任务类型：{task_type}，结束原因：{completion_reason}，"
                f"输入 Token：{input_tokens}，输出 Token：{output_tokens}，"
                f"其中推理 Token：{reasoning_tokens}）"
            )
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        await _record_ai_usage(
            repository,
            provider,
            model,
            task_type,
            AIUsageStatus.SUCCESS,
            context=usage_context,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
        return AIGenerationResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        error_message = describe_exception(exc)
        await _record_ai_usage(
            repository=repository,
            provider=provider,
            model=model,
            context=usage_context,
            task_type=task_type,
            status=AIUsageStatus.FAILED,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            error_message=error_message,
        )
        raise


async def stream_text_with_langchain(
        repository: AIModelRepository,
        provider: AIProvider,
        model: AIModel,
        chat_prompt: ChatPromptTemplate,
        input_variables: dict[str, object],
        task_type: str,
        usage_context: AIUsageContextDTO | None = None,
) -> AsyncIterator[AITextDelta | AIGenerationResult]:
    started_at = time.perf_counter()
    # 流式调用也要在 try 外保存累计用量，确保中途异常或空正文时，失败日志
    # 仍能记录模型已经消耗的 Token，而不是统一写成 0。
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    reasoning_tokens = 0
    completion_reason = "未知"
    try:
        langchain_model = create_langchain_chat_model(
            provider=provider,
            model=model,
        )
        # 先让 chat_prompt 渲染变量，再把生成的消息交给 langchain_model  | 表示顺序管道
        chain = chat_prompt | langchain_model
        content_parts = []
        async for ai_message in chain.astream(input_variables):
            # 当前块可能是正文，也可能只是携带 Token 用量的空块。
            chunk_text = ai_message.text
            if chunk_text:
                # 保存一份，用于最后拼出完整回答并写入数据库。
                content_parts.append(chunk_text)
                # 同时立即交给 Service，Service 再发送给前端。
                yield AITextDelta(content=chunk_text)
            usage = ai_message.usage_metadata or {}
            if usage:
                input_tokens = int(usage.get("input_tokens", 0) or 0)
                output_tokens = int(usage.get("output_tokens", 0) or 0)
                total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
                output_token_details = usage.get("output_token_details") or {}
                if isinstance(output_token_details, dict):
                    reasoning_tokens = int(output_token_details.get("reasoning", 0) or 0)

            # 结束原因通常只出现在最后一个流式消息块；有值时再覆盖，避免前面
            # 不含元数据的正文块把已经取得的原因重置成“未知”。
            response_metadata = ai_message.response_metadata or {}
            current_completion_reason = (
                response_metadata.get("finish_reason")
                or response_metadata.get("stop_reason")
                or response_metadata.get("status")
            )
            if current_completion_reason:
                completion_reason = str(current_completion_reason)
        content = "".join(content_parts).strip()
        if not content:
            raise RuntimeError(
                "AI 模型未返回可用正文"
                f"（任务类型：{task_type}，结束原因：{completion_reason}，"
                f"输入 Token：{input_tokens}，输出 Token：{output_tokens}，"
                f"其中推理 Token：{reasoning_tokens}）"
            )
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        await _record_ai_usage(
            repository=repository,
            provider=provider,
            model=model,
            task_type=task_type,
            status=AIUsageStatus.SUCCESS,
            context=usage_context,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
        yield AIGenerationResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        error_message = describe_exception(exc)
        await _record_ai_usage(
            repository=repository,
            provider=provider,
            model=model,
            task_type=task_type,
            context=usage_context,
            status=AIUsageStatus.FAILED,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            error_message=error_message
        )
        raise
