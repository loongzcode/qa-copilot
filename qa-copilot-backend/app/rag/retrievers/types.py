from dataclasses import dataclass

from app.core.constants import KnowledgeDocumentType


@dataclass(slots=True)
class KnowledgeSearchCandidate:
    """检索流程内部候选项，保存各阶段分数，不直接作为 API 响应。

    同一切片会依次经过向量召回、全文召回、RRF 和 Rerank。保留每一阶段
    的分数便于融合、调试和记录日志；slots=True 还能避免意外增加字段。
    """

    # 切片、文档和模块信息共同构成一条可展示、可追溯的引用。
    chunk_id: int
    document_id: int
    document_title: str
    document_type: KnowledgeDocumentType
    module_id: int | None
    module_name: str | None
    chunk_index: int
    section_title: str | None
    page_no: int | None
    content: str
    # 候选可能只经过部分阶段，所以各阶段分数都允许为空。
    vector_score: float | None = None
    full_text_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None


@dataclass(slots=True)
class KnowledgeContext:
    """准备交给大模型的知识上下文，并保留引用编号对应的原始切片。"""

    context_text: str
    sources: list[KnowledgeSearchCandidate]