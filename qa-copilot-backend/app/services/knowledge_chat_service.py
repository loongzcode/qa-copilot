import asyncio
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
)

from app.core.config import settings
from app.core.constants import (
    AIModelTaskType,
    KnowledgeChatMessageRole,
    KnowledgeChatMessageStatus,
    KnowledgeChatSessionStatus,
    KnowledgeChatStreamEventType,
    KnowledgeChatStreamStage,
)
from app.exceptions import BadRequestException, NotFoundException
from app.exceptions.errors import describe_exception
from app.models import AIModel, KnowledgeChatMemorySummary, KnowledgeChatMessage, KnowledgeChatSession, User
from app.models.mixins import utc_now
from app.rag.retrievers import KnowledgeSearchCandidate
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.knowledge_chat_repository import KnowledgeChatRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.schemas.dto.knowledge_chat import (
    KnowledgeChatMessageCreateDTO,
    KnowledgeChatSessionCreateDTO,
    KnowledgeChatSessionUpdateDTO,
)
from app.schemas.vo.knowledge_chat import (
    KnowledgeChatMessageCursorVO,
    KnowledgeChatMessageVO,
    KnowledgeChatSendResultVO,
    KnowledgeChatSessionVO,
    KnowledgeChatStreamCitationsVO,
    KnowledgeChatStreamDeltaVO,
    KnowledgeChatStreamErrorVO,
    KnowledgeChatStreamStatusVO,
    KnowledgeCitationVO,
)
from app.services.knowledge_chat_memory_service import KnowledgeChatMemoryService
from app.services.knowledge_search_service import KnowledgeSearchService
from app.utils.ai_client_util import (
    AIGenerationResult,
    AITextDelta,
    generate_text_with_langchain,
    stream_text_with_langchain,
)
from app.utils.token_util import count_text_tokens
from app.workers.knowledge_chat_memory_dispatcher import enqueue_knowledge_chat_memory_compression

logger = logging.getLogger(__name__)

type KnowledgeChatStreamPayload = (
    KnowledgeChatStreamStatusVO
    | KnowledgeChatStreamDeltaVO
    | KnowledgeChatStreamCitationsVO
    | KnowledgeChatStreamErrorVO
    | KnowledgeChatSendResultVO
)

type KnowledgeChatStreamEvent = tuple[
    KnowledgeChatStreamEventType,
    KnowledgeChatStreamPayload,
]


@dataclass(slots=True)
class KnowledgeChatGenerationResult:
    """Service 内部使用的 AI 回答生成结果。"""

    answer: str
    citations: list[KnowledgeCitationVO]
    model_id: int | None
    prompt_template_id: int | None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


type KnowledgeChatAnswerStreamItem = KnowledgeChatStreamEvent | KnowledgeChatGenerationResult


class KnowledgeChatService:
    """编排知识检索、上下文组装、模型问答和引用转换。"""

    def __init__(
        self,
        search_service: KnowledgeSearchService,
        ai_model_repository: AIModelRepository,
        prompt_template_repository: PromptTemplateRepository,
        repository: KnowledgeChatRepository,
        knowledge_base_repository: KnowledgeBaseRepository,
        memory_service: KnowledgeChatMemoryService,
    ) -> None:
        self.search_service = search_service
        self.ai_model_repository = ai_model_repository
        self.prompt_template_repository = prompt_template_repository
        self.repository = repository
        self.knowledge_base_repository = knowledge_base_repository
        self.memory_service = memory_service

    @staticmethod
    def _build_citations(
        answer_text: str,
        sources: list[KnowledgeSearchCandidate],
    ) -> list[KnowledgeCitationVO]:
        raw_numbers = re.findall(
            r"\[资料(\d+)\]",
            answer_text,
        )
        citations: list[KnowledgeCitationVO] = []
        seen_numbers: set[int] = set()
        for raw_number in raw_numbers:
            number = int(raw_number)
            if number in seen_numbers:
                continue
            # 防止模型生成 [资料0]、[资料99] 导致列表越界。
            if number < 1 or number > len(sources):
                continue
            seen_numbers.add(number)
            candidate = sources[number - 1]
            knowledge_citation = KnowledgeCitationVO(
                chunk_id=candidate.chunk_id,
                document_id=candidate.document_id,
                document_title=candidate.document_title,
                module_id=candidate.module_id,
                module_name=candidate.module_name,
                chunk_index=candidate.chunk_index,
                section_title=candidate.section_title,
                page_no=candidate.page_no,
                content=candidate.content,
                score=(candidate.rerank_score if candidate.rerank_score is not None else candidate.rrf_score or 0.0),
                source_number=number,
            )
            citations.append(knowledge_citation)
        return citations

    @staticmethod
    def _session_read(session: KnowledgeChatSession) -> KnowledgeChatSessionVO:
        return KnowledgeChatSessionVO(
            id=session.id,
            project_id=session.project_id,
            knowledge_base_id=session.knowledge_base_id,
            user_id=session.user_id,
            title=session.title,
            status=KnowledgeChatSessionStatus(session.status),
            last_message_at=session.last_message_at,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    @staticmethod
    def _message_read(message: KnowledgeChatMessage) -> KnowledgeChatMessageVO:
        citation_vos = [KnowledgeCitationVO.model_validate(citation) for citation in message.citations]
        return KnowledgeChatMessageVO(
            id=message.id,
            session_id=message.session_id,
            role=KnowledgeChatMessageRole(message.role),
            content=message.content,
            citations=citation_vos,
            model_id=message.model_id,
            prompt_template_id=message.prompt_template_id,
            status=KnowledgeChatMessageStatus(message.status),
            token_count=message.token_count,
            error_message=message.error_message,
            created_at=message.created_at,
        )

    @staticmethod
    def _select_recent_messages(messages: list[KnowledgeChatMessage], token_budget: int) -> list[KnowledgeChatMessage]:
        """
        初始化
        → 反向遍历
        → 加入前检查预算
        → 加入并累计
        → 恢复顺序
        → 去掉开头孤立的 AI 消息
        → 返回 selected
        """
        selected = []
        used_tokens = 0
        for message in reversed(messages):
            if used_tokens + message.token_count > token_budget:
                break
            selected.append(message)
            used_tokens += message.token_count
        selected.reverse()
        if selected and selected[0].role == KnowledgeChatMessageRole.ASSISTANT.value:
            selected.pop(0)
        return selected

    @staticmethod
    def _to_langchain_messages(messages: list[KnowledgeChatMessage]) -> list[BaseMessage]:
        langchain_messages = []
        for message in messages:
            if message.role == KnowledgeChatMessageRole.USER.value:
                human_message = HumanMessage(content=message.content)
                langchain_messages.append(human_message)
            if message.role == KnowledgeChatMessageRole.ASSISTANT.value:
                ai_message = AIMessage(content=message.content)
                langchain_messages.append(ai_message)
        return langchain_messages

    @staticmethod
    def _build_memory_context(
        memories: list[KnowledgeChatMemorySummary],
    ) -> str:
        """把多条长期记忆摘要拼成可以传给 Prompt 的文本。"""

        if not memories:
            return "无相关长期记忆"

        memory_parts: list[str] = []

        for index, memory in enumerate(memories, start=1):
            memory_parts.append(f"记忆{index}：{memory.summary.strip()}")

        return "\n".join(memory_parts)

    async def _rewrite_query(
        self,
        chat_model: AIModel,
        messages: list[KnowledgeChatMessage],
        memories: list[KnowledgeChatMemorySummary],
        question: str,
        usage_context: AIUsageContextDTO,
    ) -> str:
        """把依赖上下文的追问改写成可以独立检索的问题。

        chat_model 是已经通过启用状态和知识问答能力校验的默认聊天模型；
        messages 是当前问题之前、状态为 SUCCESS 的原始历史消息；
        question 是用户本次提交的原始问题。返回值只用于知识检索，最终回答
        时仍然使用原始问题，避免模型改变用户真正想问的内容。
        """

        # 第一轮对话没有任何历史，不存在“它”“其中”“上一条”等指代对象。
        # 此时无需产生一次额外的模型调用，直接使用用户原问题进行检索。
        if not messages and not memories:
            return question

        # 问题改写只需要最近一小段对话。这里复用统一的 Token 筛选方法，
        # 避免把整个长会话都交给改写模型，增加延迟、费用和噪声。
        recent_messages = self._select_recent_messages(
            messages=messages, token_budget=settings.knowledge_chat_query_rewrite_token_budget
        )

        # 原始列表虽然不为空，但预算太小或筛选后只剩孤立 AI 消息时，
        # recent_messages 仍可能为空；没有可靠历史时继续使用原问题。
        if not recent_messages and not memories:
            return question

        # query_rewrite Prompt 使用 {conversation} 字符串变量，而不是
        # MessagesPlaceholder，因此先创建字符串片段列表。
        conversation_parts: list[str] = []
        # 长期记忆是较早对话的摘要，先放在最近对话之前。
        if memories:
            conversation_parts.append("相关长期记忆：")
            conversation_parts.append(self._build_memory_context(memories))
        if recent_messages:
            conversation_parts.append("最近对话：")
        # 按正常时间顺序遍历已筛选的历史消息。
        for message in recent_messages:
            # 数据库存储的是 USER/ASSISTANT 枚举值；改写 Prompt 中使用中文
            # 角色名，使模型能够清楚区分哪句话来自用户、哪句话来自助手。
            role_name = "用户" if message.role == KnowledgeChatMessageRole.USER.value else "助手"
            # 一条数据库消息转换成一行“角色：正文”，暂时加入片段列表。
            conversation_parts.append(f"{role_name}：{message.content}")

        # 使用换行拼成完整历史对话，作为模板中的 {conversation} 值。
        conversation = "\n".join(conversation_parts)

        # Prompt 内容由后台 Prompt 管理维护，Service 只按固定编码查询，
        # 不在 Python 代码里写死具体提示词。
        prompt_template = await self.prompt_template_repository.get_by_code(code="query_rewrite")

        # 缺少内置模板属于系统配置错误，不能静默退化后掩盖部署问题。
        if prompt_template is None:
            raise NotFoundException("Prompt 不存在")

        # 管理员主动停用模板时停止使用，避免绕过后台配置状态。
        if not prompt_template.enabled:
            raise BadRequestException("检索问题改写 Prompt 模板已停用")

        # query_rewrite 的历史已经放入 {conversation} 字符串，所以这里只有
        # system 和当前 human 模板，不再插入 MessagesPlaceholder。
        chat_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", prompt_template.system_prompt),
                ("human", prompt_template.user_prompt),
            ]
        )

        # 调用统一 LangChain 客户端生成独立问题。该工具还会记录模型、
        # Token、耗时和成功/失败状态；QUERY_REWRITE 用于区分调用日志类型。
        generation_result = await generate_text_with_langchain(
            repository=self.ai_model_repository,
            provider=chat_model.provider,
            model=chat_model,
            chat_prompt=chat_prompt,
            input_variables={
                "conversation": conversation,
                "question": question,
            },
            task_type=AIModelTaskType.QUERY_REWRITE.value,
            usage_context=usage_context,
        )

        # 工具层已经拒绝空响应并去掉首尾空格，这里直接返回改写后的正文。
        return generation_result.content

    async def _stream_answer(
        self,
        project_id: int,
        knowledge_base_id: int,
        embedding_model_id: int,
        current_user: User,
        payload: KnowledgeChatMessageCreateDTO,
        usage_context: AIUsageContextDTO,
        # 从哪个会话查询历史
        session_id: int,
        # 只查询当前用户问题之前的消息
        before_message_id: int,
    ) -> AsyncIterator[KnowledgeChatAnswerStreamItem]:
        """结合历史对话和知识库证据生成一次可追溯回答。

        完整顺序是：校验默认模型、读取当前问题之前的成功消息、改写检索
        问题、执行混合检索、构建最终 Prompt、按模型上下文窗口筛选历史、
        调用聊天模型、解析引用并返回生成结果。改写后的问题只用于检索，
        最终 Prompt 始终保留用户原问题。
        """

        # 取得系统当前的默认聊天模型。问题改写和最终知识问答复用该模型，
        # 因此这里只查询一次，后续把同一个 chat_model 传给两个调用阶段。
        chat_model = await self.ai_model_repository.get_default_model()

        # 没有默认模型时，系统不知道应该调用哪个聊天模型，直接返回配置错误。
        if chat_model is None:
            raise NotFoundException("未配置默认知识问答模型")

        # 模型自身和所属服务商必须同时启用；只启用其中一个仍然无法调用。
        if not chat_model.enabled or not chat_model.provider.enabled:
            raise BadRequestException("默认知识问答模型或服务商已停用")

        # 默认模型还必须明确声明支持知识问答，防止误用 Embedding 或
        # Rerank 模型执行文本生成。
        if AIModelTaskType.KNOWLEDGE_QA.value not in chat_model.task_types:
            raise BadRequestException("默认模型不支持知识问答")

        # 查询当前用户消息之前的最近成功消息。before_message_id 排除了
        # 当前 USER 消息和随后创建的 ASSISTANT/PENDING 占位消息。
        messages = await self.repository.list_recent_successful_messages(
            session_id=session_id,
            before_message_id=before_message_id,
            limit=settings.knowledge_chat_recent_message_limit,
        )

        yield (
            KnowledgeChatStreamEventType.STATUS,
            KnowledgeChatStreamStatusVO(
                stage=KnowledgeChatStreamStage.REWRITING,
                message="正在理解当前问题和历史对话",
            ),
        )

        # 使用用户原始问题检索当前会话中语义相关的历史摘要。
        # 此时 rewritten_query 尚未生成，因此只能使用 payload.query。
        relevant_memories = await self.memory_service.retrieve_relevant_memories(
            session_id=session_id,
            query=payload.query,
            embedding_model_id=embedding_model_id,
            # 相关记忆检索会调用 Embedding 模型，因此也要沿用本次
            # 知识问答的用户、项目、请求和回答任务标识。
            usage_context=usage_context,
        )

        memory_context = self._build_memory_context(relevant_memories)

        # 将“其中第三步是什么意思”一类依赖历史的追问改写为能够独立检索
        # 的问题；第一轮没有历史时，该方法会直接返回 payload.query。
        rewritten_query = await self._rewrite_query(
            chat_model=chat_model,
            messages=messages,
            question=payload.query,
            memories=relevant_memories,
            usage_context=usage_context,
        )

        # 改写文本来自模型，不能未经校验直接进入检索。重新构造 DTO 会再次
        # 执行非空、最大长度等规则，同时保留原请求的 top_k 和 module_id。
        search_payload = KnowledgeChatMessageCreateDTO.model_validate(
            {
                **payload.model_dump(),
                "query": rewritten_query,
            }
        )

        yield (
            KnowledgeChatStreamEventType.STATUS,
            KnowledgeChatStreamStatusVO(
                stage=KnowledgeChatStreamStage.RETRIEVING,
                message="正在检索并筛选知识资料",
            ),
        )

        # 使用改写后的 search_payload 执行权限校验、问题 Embedding、向量
        # Top 30、全文 Top 30、RRF 融合、Rerank 和上下文 Top 5 构建。
        knowledge_context = await self.search_service.build_context(
            project_id=project_id,
            knowledge_base_id=knowledge_base_id,
            current_user=current_user,
            payload=search_payload,
            usage_context=usage_context,
        )

        # 没有检索到任何知识证据时不调用最终回答模型，避免模型脱离知识库
        # 自由发挥，也避免产生一次没有业务价值的模型费用。
        if not knowledge_context.sources:
            yield KnowledgeChatGenerationResult(
                # 给用户明确、可理解的兜底回答。
                answer="知识库中未找到足够依据。",
                # 没有知识来源，自然也没有引用卡片。
                citations=[],
                # 本次没有执行最终回答调用，因此没有最终回答模型 ID。
                model_id=None,
                # 同理，本次也没有使用 rag_answer 模板生成答案。
                prompt_template_id=None,
                # 三个调用用量字段都保持为 0。
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
            )
            return

        # 基础 usage_context 由整个问答流程共用。只有到了这里，系统才
        # 知道最终有多少条资料真正进入大模型 Prompt，因此复制一份最终
        # 回答专用上下文，避免修改问题改写、Embedding 等阶段共用的对象。
        answer_usage_context = usage_context.model_copy(
            update={
                "retrieval_hit_count": len(knowledge_context.sources),
            }
        )
        # 查询最终知识问答模板。它负责规定“只根据资料回答”和引用格式等
        # 规则；模板由后台维护，Service 只依赖稳定编码 rag_answer。
        prompt_template = await self.prompt_template_repository.get_by_code(code="rag_answer")

        # 找不到内置模板时无法构造最终 Prompt，应明确报告系统配置缺失。
        if prompt_template is None:
            raise NotFoundException("未配置 RAG 知识问答 Prompt 模板")

        # 已停用模板不能继续参与生成，保持运行行为与后台配置一致。
        if not prompt_template.enabled:
            raise BadRequestException("RAG 知识问答 Prompt 模板已停用")

        # 最终 Prompt 的消息顺序是：系统规则、历史对话、当前知识问答。
        # history 是运行时插槽，会展开成多条 HumanMessage/AIMessage。
        chat_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", prompt_template.system_prompt),
                MessagesPlaceholder(variable_name="history"),
                ("human", prompt_template.user_prompt),
            ]
        )

        # 先使用空历史渲染一次 Prompt，只统计无论如何都必须保留的内容：
        # system Prompt、RAG 知识上下文和用户当前原始问题。
        base_messages = chat_prompt.format_messages(
            history=[],
            context=knowledge_context.context_text,
            question=payload.query,
            memory=memory_context,
        )

        # 将每条基础消息的正文 Token 相加。这里统计的是上下文预算估算值，
        # 不是模型供应商最终用于计费的 usage.input_tokens。
        base_input_tokens = sum(count_text_tokens(str(message.content)) for message in base_messages)

        # 总上下文窗口先预留模型最大输出，再扣除消息格式/分词误差安全空间，
        # 最后扣除固定输入，剩余部分才允许装入历史对话。
        history_token_budget = (
            chat_model.context_window_tokens
            - chat_model.max_output_tokens
            - settings.knowledge_chat_context_safety_tokens
            - base_input_tokens
        )

        # 固定输入已经超过窗口时，即使不加入任何历史也无法安全调用模型。
        if history_token_budget < 0:
            raise BadRequestException("当前知识上下文超过模型上下文窗口")

        # 从已经查询过的 messages 中由近到远装入消息，直到达到历史预算；
        # 这里不会再次访问数据库。
        recent_messages = self._select_recent_messages(messages=messages, token_budget=history_token_budget)

        # SQLAlchemy 消息实体不能直接传给 LangChain，需要按照角色转换为
        # HumanMessage 和 AIMessage。
        history_messages = self._to_langchain_messages(messages=recent_messages)

        # 执行最终知识问答。context 使用检索资料，question 使用用户原话，
        # history 使用经过 Token 筛选并保留角色的最近对话。
        # generation_result = await generate_text_with_langchain(
        #     repository=self.ai_model_repository,
        #     provider=chat_model.provider,
        #     model=chat_model,
        #     chat_prompt=chat_prompt,
        #     input_variables={
        #         "context": knowledge_context.context_text,
        #         "question": payload.query,
        #         "history": history_messages,
        #     },
        #     task_type=AIModelTaskType.KNOWLEDGE_QA.value
        # )
        yield (
            KnowledgeChatStreamEventType.STATUS,
            KnowledgeChatStreamStatusVO(
                stage=KnowledgeChatStreamStage.GENERATING,
                message="正在根据知识资料生成回答",
            ),
        )
        generation_result: AIGenerationResult | None = None
        async for message in stream_text_with_langchain(
            repository=self.ai_model_repository,
            provider=chat_model.provider,
            model=chat_model,
            chat_prompt=chat_prompt,
            input_variables={
                "context": knowledge_context.context_text,
                "question": payload.query,
                "history": history_messages,
                "memory": memory_context,
            },
            task_type=AIModelTaskType.KNOWLEDGE_QA.value,
            # 最终回答日志除了请求、用户和项目，还记录实际进入
            # Prompt 的知识资料数量，便于排查“有回答但未命中资料”。
            usage_context=answer_usage_context,
        ):
            if isinstance(message, AITextDelta):
                yield (
                    KnowledgeChatStreamEventType.DELTA,
                    KnowledgeChatStreamDeltaVO(
                        content=message.content,
                    ),
                )
            else:
                generation_result = message
        if generation_result is None:
            raise RuntimeError("知识问答流缺少最终生成结果")
        # 统一调用工具返回正文和 Token 用量；content 已经过非空校验和 strip。
        answer_text = generation_result.content

        # 从回答中的 [资料N] 提取实际使用的编号，再映射回 Top 5 候选，
        # 生成前端引用卡片和数据库引用快照所需的 VO。
        citations = self._build_citations(
            answer_text=answer_text,
            sources=knowledge_context.sources,
        )

        # 返回 Service 内部生成结果。create_message() 会用它更新先前保存的
        # ASSISTANT/PENDING 占位消息，并提交第二段数据库事务。
        yield KnowledgeChatGenerationResult(
            # 模型最终回答正文。
            answer=answer_text,
            # 回答中真正引用到的知识来源。
            citations=citations,
            # 用于生成最终回答的模型主键，供消息审计追溯。
            model_id=chat_model.id,
            # 用于生成最终回答的 Prompt 模板主键。
            prompt_template_id=prompt_template.id,
            # 以下用量来自最终知识问答调用，不包含前面的 query_rewrite 调用；
            # query_rewrite 已由统一工具单独写入 ai_usage_logs。
            input_tokens=generation_result.input_tokens,
            output_tokens=generation_result.output_tokens,
            total_tokens=generation_result.total_tokens,
        )

    async def create_session(
        self,
        project_id: int,
        knowledge_base_id: int,
        current_user: User,
        payload: KnowledgeChatSessionCreateDTO,
    ) -> KnowledgeChatSessionVO:
        knowledge_base = await self.knowledge_base_repository.get_accessible_knowledge_base(
            project_id, knowledge_base_id, current_user
        )
        if knowledge_base is None:
            raise NotFoundException("知识库不存在或没有权限访问")
        if not knowledge_base.enabled:
            raise BadRequestException("知识库已停用")
        knowledge_chat_session = KnowledgeChatSession(
            project_id=project_id,
            knowledge_base_id=knowledge_base_id,
            user_id=current_user.id,
            title=payload.title,
            status=KnowledgeChatSessionStatus.ACTIVE.value,
        )
        self.repository.add(knowledge_chat_session)
        await self.repository.commit()
        await self.repository.refresh(knowledge_chat_session)
        return self._session_read(knowledge_chat_session)

    async def get_login_user_session_list(
        self,
        project_id: int,
        knowledge_base_id: int,
        current_user: User,
        status: KnowledgeChatSessionStatus | None,
        current: int,
        size: int,
    ) -> tuple[list[KnowledgeChatSessionVO], int]:
        knowledge_base = await self.knowledge_base_repository.get_accessible_knowledge_base(
            project_id,
            knowledge_base_id,
            current_user,
        )
        if knowledge_base is None:
            raise NotFoundException("知识库不存在或没有权限访问")
        sessions, total = await self.repository.list_session(
            project_id=project_id,
            knowledge_base_id=knowledge_base_id,
            user_id=current_user.id,
            status=status,
            current=current,
            size=size,
        )
        records = [self._session_read(session) for session in sessions]

        return records, total

    async def update_session_title_status(
        self,
        current_user: User,
        session_id: int,
        payload: KnowledgeChatSessionUpdateDTO,
    ) -> KnowledgeChatSessionVO:
        session = await self.repository.get_owned_session(session_id, current_user.id)
        if session is None:
            raise NotFoundException("会话不存在或没有权限访问")
        if payload.title is not None:
            session.title = payload.title
        if payload.status is not None:
            session.status = payload.status.value
        await self.repository.commit()
        await self.repository.refresh(session)
        return self._session_read(session)

    async def delete_session(
        self,
        current_user: User,
        session_id: int,
    ) -> None:
        session = await self.repository.get_owned_session(session_id, current_user.id)
        if session is None:
            raise NotFoundException("会话不存在或没有权限访问")
        session.deleted_at = utc_now()
        await self.repository.commit()

    async def list_messages(
        self,
        session_id: int,
        current_user: User,
        before_id: int | None,
        limit: int,
    ) -> KnowledgeChatMessageCursorVO:
        session = await self.repository.get_owned_session(session_id, current_user.id)
        if session is None:
            raise NotFoundException("会话不存在或没有权限访问")
        messages, has_more = await self.repository.list_messages(
            session_id,
            before_id,
            limit,
        )
        records = [self._message_read(message=message) for message in messages]
        if has_more and records:
            next_cursor = records[0].id
        else:
            next_cursor = None
        return KnowledgeChatMessageCursorVO(
            records=records,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def stream_message(
        self,
        current_user: User,
        session_id: int,
        request_id: str,
        payload: KnowledgeChatMessageCreateDTO,
    ) -> AsyncIterator[KnowledgeChatStreamEvent]:
        """用户点击“发送”后，完成一次可追踪的知识问答。

        完整业务流程：

        1. 根据 session_id 和当前登录用户查询会话。
           查询条件中包含 user_id，因此用户不能向别人的会话发送消息。
        2. 校验会话仍为 ACTIVE。已经归档的会话只能查看历史，不能继续提问。
        3. 重新校验会话所属知识库的访问权限和启用状态。
           权限可能在会话创建后发生变化，所以发送消息时不能只相信旧结果。
        4. 计算用户问题的 Token 数，创建两条消息：
           - USER/SUCCESS：保存用户真实问题；
           - ASSISTANT/PENDING：先保存一条“AI 正在生成”的占位消息。
        5. 原子更新会话的最近消息时间和未摘要 Token 数，然后第一次 commit。
           这次提交发生在调用 AI 之前，确保即使模型超时或服务进程崩溃，
           用户的问题和待处理的 AI 消息仍然有数据库记录可供恢复与排查。
        6. 执行完整 RAG 问答：检索知识片段、Rerank、构建上下文、读取
           Prompt 和默认知识问答模型，再调用模型生成带 [资料N] 的回答。
        7. 优先使用模型返回的 output_tokens；服务商没有返回时，才在本地
           估算回答 Token 数。同时把引用 VO 转成可写入 JSONB 的引用快照。
        8. 生成成功时，把 ASSISTANT 消息从 PENDING 改为 SUCCESS，并写入：
           回答正文、引用快照、模型 ID、Prompt 模板 ID 和回答 Token 数。
           同时累加会话的未摘要 Token 数，然后第二次 commit。
        9. 生成失败时，先 rollback 当前未提交修改，再通过消息 ID 重新查询
           占位消息，将其改为 FAILED 并保存错误摘要，最后继续抛出原异常。
           这样前端能收到失败响应，数据库也不会留下永久 PENDING 的消息。
        10. 成功后把数据库中的 USER 消息和 ASSISTANT 消息一起转换成 VO 返回。
            前端因此能够获得两条消息真实的 ID、创建时间、状态和引用信息。

        这里使用两次 commit，是为了把“用户已经发送问题”和“AI 是否回答
        成功”分成两个可追踪阶段，而不是让一次耗时的外部模型调用长期占用
        数据库事务。
        """
        yield (
            KnowledgeChatStreamEventType.STATUS,
            KnowledgeChatStreamStatusVO(
                stage=KnowledgeChatStreamStage.SAVING,
                message="正在保存问题",
            ),
        )
        session = await self.repository.get_owned_session(session_id, current_user.id)
        if session is None:
            raise NotFoundException("会话不存在或没有权限访问")
        if session.status != KnowledgeChatSessionStatus.ACTIVE.value:
            raise BadRequestException("归档会话不能继续发送消息")
        knowledge_base = await self.knowledge_base_repository.get_accessible_knowledge_base(
            session.project_id, session.knowledge_base_id, current_user
        )
        if knowledge_base is None:
            raise NotFoundException("知识库不存在或没有权限访问")
        if not knowledge_base.enabled:
            raise BadRequestException("知识库已停用")
        now = utc_now()
        user_token_count = count_text_tokens(payload.query)

        user_message = KnowledgeChatMessage(
            session_id=session.id,
            role=KnowledgeChatMessageRole.USER.value,
            content=payload.query,
            citations=[],
            model_id=None,
            prompt_template_id=None,
            status=KnowledgeChatMessageStatus.SUCCESS.value,
            token_count=user_token_count,
            error_message=None,
            created_at=now,
        )

        assistant_message = KnowledgeChatMessage(
            session_id=session.id,
            role=KnowledgeChatMessageRole.ASSISTANT.value,
            content="",
            citations=[],
            model_id=None,
            prompt_template_id=None,
            status=KnowledgeChatMessageStatus.PENDING.value,
            token_count=0,
            error_message=None,
            created_at=now,
        )
        self.repository.add(user_message)
        self.repository.add(assistant_message)
        unsummarized_token_count = await self.repository.touch_session(session.id, now, user_token_count)
        if unsummarized_token_count is None:
            await self.repository.rollback()
            raise NotFoundException("会话已被删除")
        await self.repository.commit()
        await self.repository.refresh(user_message)
        await self.repository.refresh(assistant_message)
        chat_session_id = session.id
        assistant_message_id = assistant_message.id
        usage_context = AIUsageContextDTO(
            request_id=request_id,
            user_id=current_user.id,
            project_id=session.project_id,
            task_id=f"knowledge_chat_answer:{assistant_message_id}",
        )
        try:
            # 调用 RAG 生成流程，取得 AI 回答、引用、模型和 Token 统计。
            generation: KnowledgeChatGenerationResult | None = None

            async for stream_item in self._stream_answer(
                project_id=session.project_id,
                knowledge_base_id=session.knowledge_base_id,
                embedding_model_id=knowledge_base.embedding_model_id,
                current_user=current_user,
                payload=payload,
                session_id=chat_session_id,
                before_message_id=user_message.id,
                usage_context=usage_context,
            ):
                if isinstance(
                    stream_item,
                    KnowledgeChatGenerationResult,
                ):
                    # 最后一项是完整生成结果，留给下面写数据库。
                    generation = stream_item
                else:
                    # STATUS 和 DELTA 继续交给 API。
                    yield stream_item

            if generation is None:
                raise RuntimeError("知识问答流缺少最终生成结果")

            # 优先使用模型服务商返回的实际输出 Token 数。
            # 部分兼容 OpenAI 协议的服务不返回 usage，此时才本地估算。
            if generation.output_tokens > 0:
                assistant_token_count = generation.output_tokens
            else:
                assistant_token_count = count_text_tokens(generation.answer)

            # citations 是 VO 列表，而数据库 JSONB 字段需要可 JSON 序列化的
            # dict 列表。这里保存“引用快照”，即使以后重建文档切片，
            # 历史回答仍然能展示当时真正使用的资料。
            citation_snapshots = [citation.model_dump(mode="json", by_alias=False) for citation in generation.citations]

            # 模型回答和引用已经准备完毕，接下来才真正进入“保存结果”阶段。
            # 这个事件必须位于生成完成之后，避免前端过早显示“正在保存回答”。
            yield (
                KnowledgeChatStreamEventType.STATUS,
                KnowledgeChatStreamStatusVO(
                    stage=KnowledgeChatStreamStage.SAVING_RESULT,
                    message="正在保存回答和引用信息",
                ),
            )

            # 把之前创建的 ASSISTANT/PENDING 占位消息更新为成功消息。
            assistant_message.content = generation.answer
            assistant_message.citations = citation_snapshots
            assistant_message.model_id = generation.model_id
            assistant_message.prompt_template_id = generation.prompt_template_id
            assistant_message.status = KnowledgeChatMessageStatus.SUCCESS.value
            assistant_message.token_count = assistant_token_count
            assistant_message.error_message = None

            # 累加 AI 回答的 Token，供后续判断是否需要进行会话记忆压缩。
            # 如果用户在 AI 生成期间并发删除了会话，touch_session
            # 会返回 False；但 AI 消息仍要从 PENDING 改成 SUCCESS，
            # 避免留下永久卡死的占位记录。
            unsummarized_token_count = await self.repository.touch_session(
                chat_session_id,
                utc_now(),
                assistant_token_count,
            )

            # 第二次事务提交：保存 AI 回答和会话 Token 增量。
            await self.repository.commit()
        except asyncio.CancelledError:
            # 浏览器主动离开或代理断开时，StreamingResponse 会取消当前生成器。
            # 明确把占位消息收口为 FAILED，避免数据库永久停留在 PENDING；
            # 用户重新进入会话后能看到可重试状态，而不是一直“正在生成”。
            await self.repository.rollback()
            cancelled_message = await self.repository.get_message(chat_session_id, assistant_message_id)
            if cancelled_message is not None:
                cancelled_message.status = KnowledgeChatMessageStatus.FAILED.value
                cancelled_message.content = ""
                cancelled_message.citations = []
                cancelled_message.token_count = 0
                cancelled_message.error_message = "客户端连接已断开，回答生成已取消，请重新发送"
                await self.repository.commit()
            raise
        except Exception as exc:
            # 流式响应已经发送过 STATUS 或 DELTA，此时 HTTP 响应头已经确定。
            # 因此这里不能再返回普通 HTTP 错误 JSON，而要更新消息状态后
            # 主动发送一个 SSE ERROR 事件。

            # 先撤销当前尚未提交的 ORM 修改，让数据库 Session 恢复到
            # 可以继续执行查询和提交的状态。
            await self.repository.rollback()

            # 错误摘要只提取一次：数据库保存截断后的内容，前端收到完整摘要。
            error_message = describe_exception(exc)

            # rollback 可能使原 assistant_message ORM 对象过期，所以不继续
            # 依赖它，而是使用第一次 commit 后保存的基本类型 ID 重新查询。
            failed_message = await self.repository.get_message(
                chat_session_id,
                assistant_message_id,
            )

            # 如果消息已被并发删除，前端仍能收到错误提示，只是没有数据库
            # 消息可以替换；因此这里先准备一个允许为 None 的 VO 变量。
            failed_message_vo: KnowledgeChatMessageVO | None = None

            if failed_message is not None:
                # 把先前的 ASSISTANT/PENDING 恢复点更新成明确的 FAILED 状态。
                failed_message.status = KnowledgeChatMessageStatus.FAILED.value
                failed_message.content = ""
                failed_message.citations = []
                failed_message.token_count = 0
                failed_message.error_message = error_message[:4000]

                await self.repository.commit()

                # refresh 后再转换 VO，确保前端取得数据库实际保存的状态。
                await self.repository.refresh(failed_message)

                failed_message_vo = self._message_read(failed_message)

            # SSE ERROR 代替普通 HTTP 错误响应。assistant_message 可以让
            # 前端直接用真实 FAILED 记录替换页面中的临时占位消息。
            yield (
                KnowledgeChatStreamEventType.ERROR,
                KnowledgeChatStreamErrorVO(
                    message=error_message,
                    assistant_message=failed_message_vo,
                ),
            )

            # 失败后必须结束生成器，否则会继续发送 CITATIONS 和 DONE。
            return

        # 判断累计 Token 是否达到 压缩的限制
        if (
            unsummarized_token_count is not None
            and unsummarized_token_count >= settings.knowledge_chat_memory_trigger_tokens
        ):
            try:
                # 达到了进行会话压缩
                await enqueue_knowledge_chat_memory_compression(chat_session_id)
            # 压缩报错了发送运行错误日志
            except Exception:
                logger.exception(
                    "知识问答记忆压缩任务投递失败：session_id=%s，unsummarized_token_count=%s",
                    chat_session_id,
                    unsummarized_token_count,
                )

        # 只有“生成回答 + 保存成功消息”已经提交后才会走到这里。
        # refresh 或 VO 转换如果意外失败，不能反过来把已成功的 AI
        # 消息标记为 FAILED，所以它们故意放在上面的 try/except 之外。
        await self.repository.refresh(assistant_message)
        result = KnowledgeChatSendResultVO(
            user_message=self._message_read(user_message),
            assistant_message=self._message_read(assistant_message),
        )
        yield (
            KnowledgeChatStreamEventType.CITATIONS,
            KnowledgeChatStreamCitationsVO(
                citations=result.assistant_message.citations,
            ),
        )
        yield (
            KnowledgeChatStreamEventType.DONE,
            result,
        )
