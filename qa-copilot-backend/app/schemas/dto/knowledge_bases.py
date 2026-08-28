from typing import Any

from pydantic import Field, field_validator, model_validator

from app.core.constants import KnowledgeDocumentType, KnowledgeVisibility
from app.schemas.camel_model import CamelModel


class KnowledgeBaseBaseDTO(CamelModel):
    """创建和编辑知识库共用的字段。"""

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    visibility: KnowledgeVisibility = KnowledgeVisibility.PROJECT
    embedding_model_id: int = Field(gt=0)
    rerank_model_id: int | None = Field(default=None, gt=0)
    enabled: bool = True

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class KnowledgeBaseCreateDTO(KnowledgeBaseBaseDTO):
    """创建知识库时接收的参数。"""


class KnowledgeBaseUpdateDTO(CamelModel):
    """编辑知识库；只更新请求中实际传入的字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    visibility: KnowledgeVisibility | None = None
    embedding_model_id: int | None = Field(default=None, gt=0)
    rerank_model_id: int | None = Field(default=None, gt=0)
    enabled: bool | None = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> KnowledgeBaseUpdateDTO:
        """字段可以不传，但数据库必填字段不能被显式更新成 null。"""

        required_fields = {
            "name",
            "description",
            "visibility",
            "embedding_model_id",
            "enabled",
        }
        invalid_fields = [
            field_name
            for field_name in required_fields
            if field_name in self.model_fields_set
            and getattr(self, field_name) is None
        ]
        if invalid_fields:
            raise ValueError(
                f"以下字段不能设置为空：{', '.join(sorted(invalid_fields))}"
            )
        return self


class KnowledgeSearchDTO(CamelModel):
    """知识库检索请求参数。

    DTO 只描述“前端允许传什么”，不包含权限校验、Embedding 或数据库查询。
    CamelModel 会把 Python 的 top_k/module_id 转换为前端使用的 topK/moduleId。
    """

    # query 是后续生成查询向量的原始文本；先去空格，再执行长度校验。
    query: str = Field(
        min_length=1,
        max_length=2000,
        description="用户输入的检索问题",
    )
    # top_k 控制最终返回数量，不等于向量/全文阶段各自召回的候选数量。
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
        description="最终返回的相关切片数量",
    )
    # 不传表示检索整个知识库；传入后只检索该功能模块关联的文档。
    module_id: int | None = Field(
        default=None,
        gt=0,
        description="可选；只检索指定功能模块关联的文档",
    )
    document_types: list[KnowledgeDocumentType] = Field(
        default_factory=list,
        max_length=len(KnowledgeDocumentType),
        description= "可选；只检索指定知识类型，空列表表示全部"
    )



    @field_validator("query", mode="before")
    @classmethod
    def strip_query(cls, value: Any) -> Any:
        """去掉问题首尾空格；全空格内容会被 min_length 拒绝。"""

        return value.strip() if isinstance(value, str) else value

