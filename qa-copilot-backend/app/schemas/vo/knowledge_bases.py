from datetime import datetime

from app.core.constants import KnowledgeVisibility
from app.schemas.camel_model import CamelModel
from pydantic import Field


class KnowledgeBaseVO(CamelModel):
    """返回给前端的知识库信息。"""

    id: int
    project_id: int
    name: str
    description: str
    visibility: KnowledgeVisibility
    embedding_model_id: int
    embedding_model_name: str
    rerank_model_id: int | None
    rerank_model_name: str | None
    document_count: int = Field(default=0, ge=0)
    chunk_count: int = Field(default=0, ge=0)
    enabled: bool
    created_by: int | None
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeModelOptionVO(CamelModel):
    """知识库表单可选择的已启用 AI 模型。"""

    id: int
    name: str
    model_id: str
    provider_name: str


class KnowledgeSearchResultVO(CamelModel):
    """返回给前端的一条知识库检索结果，也是后续回答引用的基础。

    文档和模块字段用于展示来源；切片字段用于展示实际命中的证据；
    score 是经过当前检索流程选出的最终分数。
    """

    # 引用定位：回答引用时通过 chunk_id 精确指向原始证据。
    chunk_id: int
    document_id: int
    document_title: str
    # 文档可以不关联功能模块，因此模块字段允许为空。
    module_id: int | None = None
    module_name: str | None = None
    # 原文定位与展示信息。
    chunk_index: int
    section_title: str | None = None
    page_no: int | None = None
    content: str
    # 保存当前检索流程的最终分数：
    # 现阶段是 rrf_score，接入 Rerank 后使用 rerank_score。
    score: float = Field(description="检索结果的最终相关性分数")

