from sqlalchemy import func, literal, or_, select

from app.core.constants import KnowledgeDocumentType
from app.models import KnowledgeDocument, KnowledgeDocumentChunk, TestModule
from app.rag.retrievers import KnowledgeSearchCandidate
from app.repositories.base_repository import BaseRepository


class KnowledgeSearchRepository(BaseRepository):
    """知识库向量检索和全文检索的数据访问层。"""

    async def vector_search(
        self,
        knowledge_base_id: int,
        query_vector: list[float],
        *,
        embedding_model_id: int,
        embedding_dimensions: int,
        index_version: int,
        module_id: int | None = None,
        document_types: list[str] | None = None,
        limit: int = 30,
    ) -> list[KnowledgeSearchCandidate]:
        """在指定知识库的兼容正式索引中召回向量最相似的候选切片。

        输入是 Service 生成的查询向量；输出是全文融合和 Rerank 使用的内部
        Candidate。Repository 只负责数据库查询，不负责权限和 API 转换。
        """

        # 1. 构造 pgvector 余弦距离表达式。此时没有执行 SQL，只是在描述
        #    “每个切片向量如何与 query_vector 比较”；距离越小越相关。
        distance_expression = KnowledgeDocumentChunk.embedding.cosine_distance(
            query_vector
        )

        # 2. 将“越小越好”的距离转换成“越大越好”的分数。
        #    label 名称与 KnowledgeSearchCandidate.vector_score 对应。
        vector_score_expression = (1 - distance_expression).label("vector_score")

        # 3. 只选择检索结果真正需要的字段，避免把 1536 维 embedding 等大字段
        #    再次从 PostgreSQL 传回 Python。
        knowledge_chunk = (
            KnowledgeDocumentChunk.id.label("chunk_id"),
            KnowledgeDocumentChunk.chunk_index,
            KnowledgeDocumentChunk.section_title,
            KnowledgeDocumentChunk.page_no,
            KnowledgeDocumentChunk.content,
        )
        knowledge_document = (
            KnowledgeDocument.id.label("document_id"),
            KnowledgeDocument.title.label("document_title"),
            KnowledgeDocument.module_id,
            KnowledgeDocument.document_type,
        )
        module_name_expression = TestModule.name.label("module_name")

        # 4. 从要排序的切片开始查询：
        #    JOIN 文档取得知识库、状态和标题；LEFT JOIN 模块是因为 module_id
        #    可以为空，未关联模块的文档也必须参加检索。
        statement = (
            select(
                *knowledge_chunk,
                *knowledge_document,
                module_name_expression,
                vector_score_expression,
            )
            .select_from(KnowledgeDocumentChunk)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeDocumentChunk.document_id,
            )
            .outerjoin(TestModule, TestModule.id == KnowledgeDocument.module_id)
        )

        # 5. 只允许当前知识库中未软删除且索引元数据兼容的正式切片参选。
        #    首次索引的文档没有正式切片，自然不会命中；重新索引过程中即使
        #    状态为 INDEXING，兼容的旧正式切片仍可以继续服务。
        conditions = [
            KnowledgeDocument.knowledge_base_id == knowledge_base_id,
            KnowledgeDocument.deleted_at.is_(None),
            KnowledgeDocumentChunk.embedding.is_not(None),
            KnowledgeDocumentChunk.embedding_model_id == embedding_model_id,
            KnowledgeDocumentChunk.embedding_dimensions == embedding_dimensions,
            KnowledgeDocumentChunk.index_version == index_version,
        ]
        if document_types:
            conditions.append(
                KnowledgeDocument.document_type.in_(document_types),
            )
        # 6. 不传 module_id 时检索整个知识库；传入时才追加模块过滤。
        if module_id is not None:
            conditions.append(KnowledgeDocument.module_id == module_id)

        # 7. 按原始距离升序并限制候选数。pgvector 的 HNSW 索引更容易识别
        #    “距离表达式 ORDER BY + LIMIT”这种查询形式。
        statement = (
            statement.where(*conditions)
            .order_by(distance_expression.asc())
            .limit(limit)
        )

        # 8. 前面都只是在组装 SQL；execute() 才真正访问 PostgreSQL。
        #    mappings() 让结果按 label 名称读取，而不是依赖容易出错的数字下标。
        result = await self.session.execute(statement)
        rows = result.mappings().all()

        # 9. Repository 返回内部 Candidate；Service 再负责融合、重排和 VO 转换。
        candidates = [
            KnowledgeSearchCandidate(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                document_title=row["document_title"],
                module_id=row["module_id"],
                module_name=row["module_name"],
                chunk_index=row["chunk_index"],
                section_title=row["section_title"],
                page_no=row["page_no"],
                content=row["content"],
                vector_score=float(row["vector_score"]),
                document_type=KnowledgeDocumentType(
                    row["document_type"]
                ),
            )
            for row in rows
        ]
        return candidates

    # 全文检索
    #   参数                      用途
    #| `knowledge_base_id` | 防止检索到其他知识库 |
    #| `query_text` | 用户原始问题，不生成向量 |
    #| `module_id` | 可选模块过滤 |
    #| `limit` | 第一轮召回30条 |
    #| 返回值 | 全文候选列表 |
    async def full_text_search(
            self,
            knowledge_base_id: int,
            query_text: str,
            *,
            embedding_model_id: int,
            embedding_dimensions: int,
            index_version: int,
            module_id: int | None = None,
            document_types: list[str] | None = None,
            limit: int = 30,
    ) -> list[KnowledgeSearchCandidate]:

        ts_query_expression = func.websearch_to_tsquery(
            "simple",
            query_text,
        )
        # 当前切片的search_vector
        # 是否满足
        # 用户的tsquery
        ts_match_expression = (
            KnowledgeDocumentChunk.search_vector
            .bool_op("@@")(ts_query_expression)
        )
        # 计算匹配得分
        # ts_rank_cd() 根据词元命中情况计算相关度。
        # coalesce(..., 0.0)表示：
        # 如果分数是NULL，就使用0.0
        ts_score_expression = func.coalesce(
            func.ts_rank_cd(
                KnowledgeDocumentChunk.search_vector,
                ts_query_expression,
            ),
            0.0,
        )
        # 再接着进行pg_tram匹配
        query_literal = literal(query_text)
        # 判断查询是否与四个字段中的任意一个相似：
        # <% 的意思是：
        # 左边的查询文本是否与右边文本中的某个连续片段足够相似
        #match_expression
        #决定“要不要”

        trigram_match_expression = or_(
            query_literal.bool_op("<%")(KnowledgeDocumentChunk.content),
            query_literal.bool_op("<%")(
                func.coalesce(KnowledgeDocumentChunk.section_title, "")
            ),
            query_literal.bool_op("<%")(KnowledgeDocument.title),
            query_literal.bool_op("<%")(
                func.coalesce(TestModule.name, "")
            ),
        )
        #score_expression
        #决定“排第几”
         # 计算分数
        content_score = func.word_similarity(
            query_text,
            KnowledgeDocumentChunk.content,
        )

        section_score = func.word_similarity(
            query_text,
            func.coalesce(
                KnowledgeDocumentChunk.section_title,
                "",
            ),
        )

        document_title_score = func.word_similarity(
            query_text,
            KnowledgeDocument.title,
        )

        module_name_score = func.word_similarity(
            query_text,
            func.coalesce(
                TestModule.name,
                "",
            ),
        )
        # greatest() 的意思是：
        # 正文分数、章节分数、文档标题分数、模块名分数
        # → 选择最高的一个
        trigram_score_expression = func.greatest(
            content_score,
            section_score,
            document_title_score,
            module_name_score,
        )
        full_text_score_expression = (
                ts_score_expression + trigram_score_expression
        ).label("full_text_score")

        knowledge_chunk = (
            KnowledgeDocumentChunk.id.label("chunk_id"),
            KnowledgeDocumentChunk.chunk_index,
            KnowledgeDocumentChunk.section_title,
            KnowledgeDocumentChunk.page_no,
            KnowledgeDocumentChunk.content,
        )
        knowledge_document = (
            KnowledgeDocument.id.label("document_id"),
            KnowledgeDocument.title.label("document_title"),
            KnowledgeDocument.module_id,
            KnowledgeDocument.document_type,
        )
        module_name_expression = TestModule.name.label("module_name")

        # 4. 从要排序的切片开始查询：
        #    JOIN 文档取得知识库、状态和标题；LEFT JOIN 模块是因为 module_id
        #    可以为空，未关联模块的文档也必须参加检索。
        statement = (
            select(
                *knowledge_chunk,
                *knowledge_document,
                module_name_expression,
                full_text_score_expression,
            )
            .select_from(KnowledgeDocumentChunk)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeDocumentChunk.document_id,
            )
            .outerjoin(TestModule, TestModule.id == KnowledgeDocument.module_id)
        )

        # 5. 只保留词法检索命中的切片
        conditions = [
            KnowledgeDocument.knowledge_base_id == knowledge_base_id,
            KnowledgeDocument.deleted_at.is_(None),
            # 与向量检索保持相同语义：后台任务状态不应让仍兼容的正式索引
            # 下线；没有正式切片的新文档本身也不会命中该查询。
            # 全文检索也限定同一套索引元数据，避免混合检索把旧模型或旧切片
            # 版本的结果重新带回候选集合。
            KnowledgeDocumentChunk.embedding_model_id == embedding_model_id,
            KnowledgeDocumentChunk.embedding_dimensions == embedding_dimensions,
            KnowledgeDocumentChunk.index_version == index_version,
            # 两种词法检索任意一种命中即可：
            # 1. PostgreSQL 全文检索命中；
            # 2. pg_trgm 相似度检索命中。
            or_(
                ts_match_expression,
                trigram_match_expression,
            ),
        ]
        if document_types:
            conditions.append(
                KnowledgeDocument.document_type.in_(document_types),
            )
        # 6. 不传 module_id 时检索整个知识库；传入时才追加模块过滤。
        if module_id is not None:
            conditions.append(KnowledgeDocument.module_id == module_id)

        # 7. 按词法相关度降序取 Top N
        statement = (
            statement.where(*conditions)
            .order_by(
                full_text_score_expression.desc(),
                KnowledgeDocumentChunk.id.asc(),
            )
            .limit(limit)
        )

        # 8. 前面都只是在组装 SQL；execute() 才真正访问 PostgreSQL。
        #    mappings() 让结果按 label 名称读取，而不是依赖容易出错的数字下标。
        result = await self.session.execute(statement)
        rows = result.mappings().all()

        # 9. Repository 返回内部 Candidate；Service 再负责融合、重排和 VO 转换。
        candidates = [
            KnowledgeSearchCandidate(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                document_title=row["document_title"],
                module_id=row["module_id"],
                module_name=row["module_name"],
                chunk_index=row["chunk_index"],
                section_title=row["section_title"],
                page_no=row["page_no"],
                content=row["content"],
                full_text_score=float(row["full_text_score"]),
                document_type=KnowledgeDocumentType(
                    row["document_type"]
                ),
            )
            for row in rows
        ]
        return candidates
