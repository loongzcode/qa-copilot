from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    literal,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, query_expression, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.ai_model import AIModel
    from app.models.test_projects import TestProjects
    from app.models.user import User


class KnowledgeBase(TimestampMixin, Base):
    """项目知识库。

    知识库只保存检索配置和业务属性。文档数、切片数以及关联对象名称
    都通过查询动态填充，避免在多张表中重复保存容易失真的统计数据。
    """

    __tablename__ = "knowledge_bases"

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "name",
            name="uq_knowledge_bases_project_name",
        ),
        CheckConstraint(
            "visibility IN ('PROJECT', 'MANAGERS', 'PRIVATE')",
            name="chk_knowledge_bases_visibility",
        ),
        Index(
            "ix_knowledge_bases_project_enabled",
            "project_id",
            "enabled",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
    )
    visibility: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PROJECT",
        server_default=text("'PROJECT'"),
    )
    embedding_model_id: Mapped[int] = mapped_column(
        ForeignKey("ai_models.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rerank_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"),
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    project: Mapped[TestProjects] = relationship(
        "TestProjects",
        foreign_keys=[project_id],
        lazy="selectin",
    )
    embedding_model: Mapped[AIModel] = relationship(
        "AIModel",
        foreign_keys=[embedding_model_id],
        lazy="selectin",
    )
    rerank_model: Mapped[AIModel | None] = relationship(
        "AIModel",
        foreign_keys=[rerank_model_id],
        lazy="selectin",
    )
    creator: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="selectin",
    )

    # 这两个属性不是 knowledge_bases 的真实字段，由列表查询动态填充。
    document_count: Mapped[int] = query_expression(literal(0))
    chunk_count: Mapped[int] = query_expression(literal(0))
