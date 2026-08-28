from app.core.constants import (
    KNOWLEDGE_DOCUMENT_INDEX_VERSION,
    AIModelTaskType,
)
from app.exceptions import BadRequestException, NotFoundException
from app.models import User
from app.rag.retrievers.types import KnowledgeContext, KnowledgeSearchCandidate
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.knowledge_search_repository import KnowledgeSearchRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.schemas.dto.knowledge_bases import KnowledgeSearchDTO
from app.schemas.vo.knowledge_bases import KnowledgeSearchResultVO
from app.utils.ai_client_util import AIEmbeddingResult, generate_embedding, rerank_documents


class KnowledgeSearchService:
    """编排知识库权限校验、问题向量化、混合检索和重排序。"""

    def __init__(
            self,
            knowledge_base_repository: KnowledgeBaseRepository,
            ai_model_repository: AIModelRepository,
            search_repository: KnowledgeSearchRepository,
    ) -> None:
        self.knowledge_base_repository = knowledge_base_repository
        self.ai_model_repository = ai_model_repository
        self.search_repository = search_repository

    @staticmethod
    def _rrf_fuse(
            vector_candidates: list[KnowledgeSearchCandidate],
            full_text_candidates: list[KnowledgeSearchCandidate],
            *,
            rrf_k: int = 60,
    ) -> list[KnowledgeSearchCandidate]:

        # 创建以 chunk_id 为键的候选字典
        candidate_map: dict[int, KnowledgeSearchCandidate] = {}
        # 遍历向量候选，并取得从 1 开始的排名
        # 根据排名计算 RRF 分数
        # 把分数写入 candidate.rrf_score
        # 按照 chunk_id 放入字典
        for rank, candidate in enumerate(vector_candidates, start=1):
            # 根据排名计算 RRF 分数
            rank_score = 1.0 / (rrf_k + rank)
            # 把分数写入 candidate.rrf_score
            candidate.rrf_score = rank_score
            candidate_map[candidate.chunk_id] = candidate
        # 遍历词法候选，并取得从 1 开始的排名
        # 计算当前词法排名的 RRF 分数
        # 根据 chunk_id 查找是否已经存在
        for rank, candidate in enumerate(full_text_candidates, start=1):
            # 计算当前词法排名的 RRF 分数
            rank_score = 1.0 / (rrf_k + rank)
            # 如果已经存在
            # 把词法候选的 full_text_score 复制给已有候选
            # 在原有 rrf_score 上累加当前排名分数
            existing = candidate_map.get(candidate.chunk_id)
            if existing is not None:
                existing.full_text_score = candidate.full_text_score
                existing.rrf_score = ((existing.rrf_score or 0.0) + rank_score)
            # 如果不存在
            # 给当前词法候选设置 rrf_score
            # 放入字典
            else:
                candidate.rrf_score = rank_score
                candidate_map[candidate.chunk_id] = candidate
        # 取出字典中的所有候选
        # 按 rrf_score 从高到低排序并返回
        return sorted(
            candidate_map.values(),
            # 排序时看 candidate.rrf_score
            # 如果它是 None，就按 0.0 处理
            key=lambda candidate: candidate.rrf_score or 0.0,
            reverse=True,
        )

    async def _rerank_candidates(
            self,
            query: str,
            candidates: list[KnowledgeSearchCandidate],
            rerank_model_id: int | None,
            usage_context: AIUsageContextDTO | None = None,
            *,
            limit: int = 10,
    ) -> list[KnowledgeSearchCandidate]:
        """使用知识库配置的 Rerank 模型对融合候选进行精排。"""
        # 如果没配置 Rerank 模型，直接返回 RRF 结果
        # 如果没有候选，也直接返回
        if rerank_model_id is None or not candidates:
            return candidates
        # 根据 rerank_model_id 查询模型
        # 模型不存在则报错
        # 模型或服务商停用则报错
        # 模型不支持 RERANK 则报错
        rerank_model = await self.ai_model_repository.get_model(rerank_model_id)
        if rerank_model is None:
            raise NotFoundException("RERANK 模型不存在")
        if not rerank_model.enabled or not rerank_model.provider.enabled:
            raise BadRequestException("模型或服务商停用")
        if AIModelTaskType.RERANK.value not in rerank_model.task_types:
            raise BadRequestException("模型不支持Rerank")

        # 从 RRF 候选中截取前 limit 条
        # 提取每条候选的 content，组成 documents
        rerank_inputs = candidates[:limit]
        documents: list[str] = []

        for candidate in rerank_inputs:
            document_parts = [
                f"文档类型：{candidate.document_type.value}",
                f"文档标题：{candidate.document_title}",
            ]
            if candidate.module_name is not None:
                document_parts.append(
                    f"所属模块：{candidate.module_name}"
                )
            if candidate.section_title is not None:
                document_parts.append(
                    f"章节：{candidate.section_title}"
                )
            document_parts.append("内容：")
            document_parts.append(candidate.content)
            # 把当前资料的多个部分拼成一个字符串，
            # 再加入最终发送给 Rerank 的 documents。
            documents.append(
                "\n".join(document_parts)
            )
        # 调用 rerank_documents：
        # query 使用用户原始问题
        # documents 使用候选正文
        # top_n 使用候选实际数量
        # task_type 使用 RERANK
        rerank_result = await rerank_documents(
            repository=self.ai_model_repository,
            provider=rerank_model.provider,
            model=rerank_model,
            query=query,
            documents=documents,
            top_n=len(rerank_inputs),
            task_type=AIModelTaskType.RERANK.value,
            usage_context=usage_context
        )
        # 创建新的 reranked_candidates 列表
        reranked_candidates = []
        # 遍历模型返回的结果：
        # 根据 item.index 从输入候选中找回原对象
        # 把 item.relevance_score 写入 candidate.rerank_score
        # 按返回顺序加入新列表
        for item in rerank_result.results:
            candidate = rerank_inputs[item.index]
            candidate.rerank_score = item.relevance_score
            reranked_candidates.append(candidate)
        # 返回新列表
        return reranked_candidates

    @staticmethod
    def _build_context(
            candidates: list[KnowledgeSearchCandidate],
            *,
            limit: int = 5,
    ) -> KnowledgeContext:
        # 1. 从排好序的 candidates 中截取前 limit 条
        selected_candidates = candidates[:limit]
        # 2. 创建 context_parts 空列表
        context_parts: list[str] = []
        # 3. enumerate(..., start=1) 遍历切片
        for source_number, candidate in enumerate(selected_candidates, start=1):
            # 4. 每条切片生成 [资料1]、[资料2] 这样的编号
            # 5. 写入文档标题
            source_parts = [
                f"[资料{source_number}]",
                f"文档类型：{candidate.document_type.value}",
                f"文档：{candidate.document_title}",
            ]

            if candidate.module_name is not None:
                source_parts.append(
                    f"所属模块：{candidate.module_name}"
                )
            # 6. section_title 不为空时写入章节
            if candidate.section_title is not None:
                source_parts.append(f"章节：{candidate.section_title}")
            # 7. page_no 不为空时写入页码
            if candidate.page_no is not None:
                source_parts.append(f"页码：{candidate.page_no}")
            # 写入正文
            source_parts.append("内容：")
            source_parts.append(candidate.content)
            context_parts.append("\n".join(source_parts))
        context_text = "\n\n".join(context_parts)
        return KnowledgeContext(
            context_text=context_text,
            sources=selected_candidates
        )

    async def _search_candidates(
            self,
            project_id: int,
            knowledge_base_id: int,
            current_user: User,
            payload: KnowledgeSearchDTO,
            usage_context: AIUsageContextDTO | None = None,
    ) -> list[KnowledgeSearchCandidate]:
        """执行权限校验、混合检索、RRF 融合和 Rerank，返回内部候选。"""

        # 1. 使用带数据权限的查询取得知识库。
        #    用户不能通过猜测 knowledge_base_id 绕过可见范围；为避免泄露资源
        #    是否真实存在，“不存在”和“无权限”统一返回相同的 404 业务错误。
        knowledge_base = await self.knowledge_base_repository.get_accessible_knowledge_base(
            project_id,
            knowledge_base_id,
            current_user,
        )
        if knowledge_base is None:
            raise NotFoundException("知识库不存在或没有权限访问")

        # 2. 已停用知识库不能继续产生模型费用，也不应该返回旧索引内容。
        if not knowledge_base.enabled:
            raise BadRequestException("知识库已停用")

        # 3. 根据知识库配置的主键重新查询 Embedding 模型。
        #    get_model() 会同时加载 provider，创建 AI 客户端需要服务商地址和密钥。
        model = await self.ai_model_repository.get_model(knowledge_base.embedding_model_id)
        if model is None:
            raise NotFoundException("模型不存在")

        # 4. 创建知识库时虽然校验过模型，但管理员之后可能停用模型或服务商，
        #    所以每次真正调用前仍需再次确认状态和 Embedding 能力。
        if not model.enabled or not model.provider.enabled:
            raise BadRequestException("Embedding模型或服务商已停用")
        if AIModelTaskType.EMBEDDING.value not in model.task_types:
            raise BadRequestException("模型不支持Embedding")

        document_type_values = [document_type.value for document_type in payload.document_types]

        # 5. 将用户问题转换成与文档切片处于同一向量空间的查询向量。
        #    generate_embedding() 还会校验返回维度并记录本次模型用量。
        embedding_result: AIEmbeddingResult = await generate_embedding(
            repository=self.ai_model_repository,
            provider=model.provider,
            model=model,
            input_text=payload.query,
            task_type=AIModelTaskType.EMBEDDING.value,
            usage_context=usage_context
        )
        query_vector: list[float] = embedding_result.vector

        # 6. 先召回距离最近的 30 条内部候选。这里不能过早只取 top_k 条，
        #    后续全文融合和 Rerank 需要一批较大的候选集合进行比较。
        vector_candidates: list[KnowledgeSearchCandidate] = await self.search_repository.vector_search(
            knowledge_base_id=knowledge_base_id,
            query_vector=query_vector,
            embedding_model_id=model.id,
            embedding_dimensions=len(query_vector),
            index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
            module_id=payload.module_id,
            document_types=document_type_values,
            limit=30
        )

        # 7. 使用用户原始问题进行词法检索。
        #    词法检索不需要问题向量，擅长匹配接口名、错误码和原文关键词。
        full_text_candidates: list[KnowledgeSearchCandidate] = (
            await self.search_repository.full_text_search(
                knowledge_base_id=knowledge_base_id,
                query_text=payload.query,
                embedding_model_id=model.id,
                embedding_dimensions=len(query_vector),
                index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
                module_id=payload.module_id,
                document_types=document_type_values,
                limit=30,
            )
        )

        # 8. 根据两路候选的排名进行融合，并按照 chunk_id 去重。
        fused_candidates = self._rrf_fuse(
            vector_candidates,
            full_text_candidates,
        )
        # 9. 调用rerank_model进行检索结果重排序选出 TOP10
        final_candidates = await self._rerank_candidates(
            query=payload.query,
            candidates=fused_candidates,
            rerank_model_id=knowledge_base.rerank_model_id,
            usage_context=usage_context
        )

        # 返回已经完成 RRF 融合和 Rerank 排序的内部候选。
        # 后面的纯检索接口和知识问答都复用这份结果。

        return final_candidates

    async def search_knowledge_base(
            self,
            project_id: int,
            knowledge_base_id: int,
            current_user: User,
            payload: KnowledgeSearchDTO,
            request_id: str,
    ) -> list[KnowledgeSearchResultVO]:
        """执行知识检索，并把内部候选转换成前端需要的 VO。"""

        # 纯检索没有持久化的回答消息可作为 task_id，但仍然可以记录
        # HTTP 请求、当前用户和所属项目，足以关联本次 Embedding/Rerank。
        usage_context = AIUsageContextDTO(
            request_id=request_id,
            user_id=current_user.id,
            project_id=project_id,
        )

        # 调用共用检索流程，取得已经完成 RRF 和 Rerank 的候选。
        candidates = await self._search_candidates(
            project_id=project_id,
            knowledge_base_id=knowledge_base_id,
            current_user=current_user,
            payload=payload,
            usage_context=usage_context,
        )

        # 纯检索接口只返回前端要求的 top_k 条结果。
        return [
            KnowledgeSearchResultVO(
                chunk_id=candidate.chunk_id,
                document_id=candidate.document_id,
                document_title=candidate.document_title,
                module_id=candidate.module_id,
                module_name=candidate.module_name,
                chunk_index=candidate.chunk_index,
                section_title=candidate.section_title,
                page_no=candidate.page_no,
                content=candidate.content,
                score=(
                    candidate.rerank_score
                    if candidate.rerank_score is not None
                    else candidate.rrf_score or 0.0
                ),
            )
            for candidate in candidates[:payload.top_k]
        ]

    async def build_context(
            self,
            project_id: int,
            knowledge_base_id: int,
            current_user: User,
            payload: KnowledgeSearchDTO,
            usage_context: AIUsageContextDTO | None = None,
    ) -> KnowledgeContext:
        """执行知识检索，并把最终 Top K 组装成大模型上下文。"""

        candidates = await self._search_candidates(
            project_id=project_id,
            knowledge_base_id=knowledge_base_id,
            current_user=current_user,
            payload=payload,
            usage_context=usage_context
        )

        return self._build_context(
            candidates,
            limit=payload.top_k,
        )
