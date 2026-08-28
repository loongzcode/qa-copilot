"""知识问答历史压缩、摘要向量化和相关记忆检索服务。"""
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.core.constants import AIModelTaskType, KnowledgeChatMemoryStatus, KnowledgeChatMessageRole
from app.exceptions import BadRequestException, NotFoundException
from app.exceptions.errors import describe_exception
from app.models import KnowledgeChatMemorySummary, KnowledgeChatMessage
from app.models.mixins import utc_now
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_chat_repository import KnowledgeChatRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.utils.ai_client_util import generate_embedding, generate_text_with_langchain
from app.utils.token_util import count_text_tokens


class KnowledgeChatMemoryService:
    def __init__(
            self,
            knowledge_chat_repository: KnowledgeChatRepository,
            ai_model_repository: AIModelRepository,
            prompt_template_repository: PromptTemplateRepository,
    ):
        self.knowledge_chat_repository = knowledge_chat_repository
        self.ai_model_repository = ai_model_repository
        self.prompt_template_repository = prompt_template_repository

    @staticmethod
    def _select_compressible_messages(
            messages: list[KnowledgeChatMessage],
            token_budget: int
    ) -> tuple[list[KnowledgeChatMessage], int]:
        # 选中用于摘要的消息
        selected_messages = []
        # 这些消息原文的 Token 总数
        selected_token_count = 0
        if token_budget <= 0:
            return selected_messages, selected_token_count
        for message in messages:
            if selected_token_count + message.token_count > token_budget:
                break
            else:
                selected_messages.append(message)
                selected_token_count += message.token_count
        # 移除最后一条消息类型是 USER的消息，保证消息的完整度
        while (
                selected_messages
                and selected_messages[-1].role
                == KnowledgeChatMessageRole.USER.value
        ):
            removed_message = selected_messages.pop()
            selected_token_count -= removed_message.token_count
        return selected_messages, selected_token_count

    @staticmethod
    def _build_transcript(
            messages: list[KnowledgeChatMessage],
    ) -> str:
        transcript_parts = []
        for message in messages:
            role_name = (
                "用户"
                if message.role == KnowledgeChatMessageRole.USER.value
                else "助手"
            )
            transcript_parts.append(
                f"{role_name}：{message.content.strip()}"
            )
        return "\n".join(transcript_parts)

    async def retrieve_relevant_memories(
            self,
            session_id: int,
            query: str,
            embedding_model_id: int,
            usage_context: AIUsageContextDTO,
    ) -> list[KnowledgeChatMemorySummary]:
        has_ready_memories = (
            await self.knowledge_chat_repository
            .has_ready_memory_summaries(session_id)
        )

        if not has_ready_memories:
            return []
        embedding_model = await self.ai_model_repository.get_model(
            embedding_model_id
        )
        if embedding_model is None:
            raise NotFoundException("未配置向量模型")
        if not embedding_model.enabled or not embedding_model.provider.enabled:
            raise BadRequestException(
                "向量模型或服务商已停用"
            )
        if AIModelTaskType.EMBEDDING.value not in embedding_model.task_types:
            raise BadRequestException("模型不支持向量检索")
        embedding_result = await generate_embedding(
            repository=self.ai_model_repository,
            provider=embedding_model.provider,
            model=embedding_model,
            input_text=query,
            task_type=AIModelTaskType.EMBEDDING.value,
            # 这次向量调用是当前知识问答的一部分，不能丢失外层链路信息。
            usage_context=usage_context,
        )
        query_vector = embedding_result.vector
        memory_summaries = (
            await self.knowledge_chat_repository
            .list_relevant_memory_summaries(
                session_id=session_id,
                query_vector=query_vector,
                limit=settings.knowledge_chat_memory_retrieval_top_k,
            )
        )
        selected_memories: list[KnowledgeChatMemorySummary] = []
        used_tokens = 0
        for memory_summary in memory_summaries:
            if used_tokens + memory_summary.token_count > settings.knowledge_chat_memory_retrieval_token_budget:
                continue
            else:
                selected_memories.append(memory_summary)
                used_tokens += memory_summary.token_count
        return selected_memories

    async def compress_session_memory(
            self,
            session_id: int,
            task_id: str,
    ) -> bool:
        knowledge_chat_session = await self.knowledge_chat_repository.get_session_for_memory(session_id)
        if knowledge_chat_session is None:
            await self.knowledge_chat_repository.rollback()
            return False
        if knowledge_chat_session.unsummarized_token_count < settings.knowledge_chat_memory_trigger_tokens:
            await self.knowledge_chat_repository.rollback()
            return False

        # 记忆压缩由 Celery Worker 执行，没有 HTTP request_id；但会话本身
        # 能提供用户和项目归属，Celery 任务 ID 则用于串联摘要生成和向量化。
        usage_context = AIUsageContextDTO(
            user_id=knowledge_chat_session.user_id,
            project_id=knowledge_chat_session.project_id,
            task_id=task_id,
        )
        # 记住任务开始时的记忆版本。
        # 摘要生成完成后会再次比较，防止覆盖其他压缩任务的结果。
        expected_memory_version = knowledge_chat_session.memory_version

        # 记住任务开始时，历史消息已经摘要到哪一条。
        expected_last_summarized_message_id = (
            knowledge_chat_session.last_summarized_message_id
        )
        # 计算可压缩 Token
        compressible_token_budget = (
                knowledge_chat_session.unsummarized_token_count
                - settings.knowledge_chat_memory_keep_recent_tokens
        )
        # 查询摘要游标之后最多 200 条成功消息
        after_messages = await self.knowledge_chat_repository.list_successful_messages_after(
            session_id,
            knowledge_chat_session.last_summarized_message_id,
            200
        )
        # 划分本次压缩消息
        selected_messages, selected_token_count = self._select_compressible_messages(
            after_messages,
            compressible_token_budget
        )
        # 选中用于摘要的消息为空就返回false
        if not selected_messages:
            await self.knowledge_chat_repository.rollback()
            return False
        from_message_id = selected_messages[0].id
        to_message_id = selected_messages[-1].id
        memory_summary = await self.knowledge_chat_repository.get_memory_summary_by_range(
            session_id,
            from_message_id,
            to_message_id,
        )
        if (
                memory_summary is not None and
                memory_summary.status in
                {
                    KnowledgeChatMemoryStatus.PENDING.value,
                    KnowledgeChatMemoryStatus.READY.value
                }
        ):
            await self.knowledge_chat_repository.rollback()
            return False
        if memory_summary is None:
            memory_summary = KnowledgeChatMemorySummary(
                session_id=session_id,
                from_message_id=from_message_id,
                to_message_id=to_message_id,
                message_count=len(selected_messages),
                summary="",
                token_count=0,
                model_id=None,
                embedding=None,
                status=KnowledgeChatMemoryStatus.PENDING.value,
                error_message=None,
            )
            self.knowledge_chat_repository.add(memory_summary)
        else:
            # 前面的判断已经排除了 PENDING 和 READY。
            # 数据库状态又只允许三种，因此走到这里的是 FAILED 记录。
            memory_summary.message_count = len(selected_messages)
            memory_summary.summary = ""
            memory_summary.token_count = 0
            memory_summary.model_id = None
            memory_summary.embedding = None
            memory_summary.status = KnowledgeChatMemoryStatus.PENDING.value
            memory_summary.error_message = None
        await self.knowledge_chat_repository.commit()
        try:
            await self.knowledge_chat_repository.refresh(memory_summary)
            memory_prompt = await self.prompt_template_repository.get_by_code(
                code="knowledge_chat_memory_summary"
            )
            # 缺少内置模板属于系统配置错误，不能静默退化后掩盖部署问题。
            if memory_prompt is None:
                raise NotFoundException("Prompt 不存在")

            # 管理员主动停用模板时停止使用，避免绕过后台配置状态。
            if not memory_prompt.enabled:
                raise BadRequestException(
                    "知识问答会话记忆摘要 Prompt 模板已停用"
                )
            ai_model = await self.ai_model_repository.get_default_model()
            # 没有默认模型时，系统不知道应该调用哪个聊天模型，直接返回配置错误。
            if ai_model is None:
                raise NotFoundException("未配置默认知识问答模型")
            if AIModelTaskType.KNOWLEDGE_QA.value not in ai_model.task_types:
                raise BadRequestException("默认模型不支持知识问答")
            # 模型自身和所属服务商必须同时启用；只启用其中一个仍然无法调用。
            if not ai_model.enabled or not ai_model.provider.enabled:
                raise BadRequestException("默认知识问答模型或服务商已停用")
            transcript = self._build_transcript(selected_messages)
            chat_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", memory_prompt.system_prompt),
                    ("human", memory_prompt.user_prompt),
                ]
            )
            generation_result  = await generate_text_with_langchain(
                repository=self.ai_model_repository,
                provider=ai_model.provider,
                model=ai_model,
                chat_prompt=chat_prompt,
                input_variables={"conversation": transcript},
                task_type=AIModelTaskType.KNOWLEDGE_QA.value,
                max_output_tokens=settings.knowledge_chat_memory_summary_max_tokens,
                usage_context=usage_context,
            )
            summary_text = generation_result.content
            # 将来把这段摘要放进问答 Prompt，会占用多少上下文空间？
            summary_token_count = count_text_tokens(summary_text)
            embedding_model = await self.ai_model_repository.get_model(
                knowledge_chat_session.knowledge_base.embedding_model_id
            )
            if embedding_model is None:
                raise NotFoundException("未配置向量模型")
            if not embedding_model.enabled or not embedding_model.provider.enabled:
                raise BadRequestException(
                    "向量模型或服务商已停用"
                )
            if AIModelTaskType.EMBEDDING.value not in embedding_model.task_types:
                raise BadRequestException("模型不支持向量检索")
            embedding_result = await generate_embedding(
                repository=self.ai_model_repository,
                provider=embedding_model.provider,
                model=embedding_model,
                input_text=summary_text,
                task_type=AIModelTaskType.EMBEDDING.value,
                usage_context=usage_context,
            )
            # 获取向量化后的摘要
            summary_embedding = embedding_result.vector
            # 保存模型生成的摘要正文。
            memory_summary.summary = summary_text

            # 保存摘要正文占用的 Token，后续拼接问答上下文时用于控制长度。
            memory_summary.token_count = summary_token_count

            # 记录“由哪个聊天模型生成了这份摘要”。
            memory_summary.model_id = ai_model.id

            # 保存摘要向量，后续可以根据用户问题检索相关的历史记忆。
            memory_summary.embedding = summary_embedding

            # 摘要正文和向量均已生成，标记为可用。
            memory_summary.status = KnowledgeChatMemoryStatus.READY.value

            # 本次执行成功，清除之前失败时留下的错误信息。
            memory_summary.error_message = None
            # 更新会话的压缩进度：
            # 1. 记录本次已经摘要到的 to_message_id:
            # 2. 记忆版本加一：
            # 3. 从未压缩 token 中扣除本次处理原始消息 token
            session_updated = (
                await self.knowledge_chat_repository.update_session_after_memory_compression(
                    session_id=session_id,
                    # 任务开始时记下的版本。
                    expected_memory_version=expected_memory_version,
                    # 任务开始时记下的摘要位置。
                    expected_last_summarized_message_id=expected_last_summarized_message_id,
                    # 本次最后摘要到哪条消息
                    to_message_id=to_message_id,
                    # 本次被压缩的原始消息 Token，要从未压缩数量中扣除。
                    compressed_token_count=selected_token_count,
                    updated_at=utc_now()
                )
            )
            # 返回false说明生成摘要期间，另一个任务已经修改了会话压缩进度
            # 当前任务不能再覆盖数据库中的最新结果
            if not session_updated:
                raise RuntimeError("会话记忆压缩进度已被其他任务更新")
            # 一次提交两部分修改：
            # 1. 将摘要记录从 PENDING 改成 READY，并保存正文和向量
            # 2. 更新会话已经压缩到哪条消息，以及剩余未压缩 token
            #
            # 两部分必须同时成功，任何一部分失败 未曾 except都会回滚
            # 避免摘要与会话进度不一致
            await self.knowledge_chat_repository.commit()
        except Exception as exc:
            await self.knowledge_chat_repository.rollback()
            memory_summary = await self.knowledge_chat_repository.get_memory_summary_by_range(
                session_id,
                from_message_id,
                to_message_id,
            )
            if memory_summary is not None:
                memory_summary.status = KnowledgeChatMemoryStatus.FAILED.value
                memory_summary.error_message = describe_exception(exc)[:4000]
                await self.knowledge_chat_repository.commit()
            raise
        return True
