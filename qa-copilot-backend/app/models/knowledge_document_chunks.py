from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import KNOWLEDGE_EMBEDDING_DIMENSIONS
from app.core.database import Base
from app.models.mixins import utc_now

if TYPE_CHECKING:
    from app.models.knowledge_documents import KnowledgeDocument


class KnowledgeDocumentChunk(Base):
    """知识文档切片，同时保存原文、全文检索字段和 1536 维向量。"""

    __tablename__ = "knowledge_document_chunks"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_knowledge_document_chunks_index",
        ),
        Index("ix_knowledge_document_chunks_document", "document_id"),
        Index(
            "ix_knowledge_document_chunks_compatibility",
            "embedding_model_id",
            "embedding_dimensions",
            "index_version",
        ),
        Index(
            "ix_knowledge_document_chunks_search",
            "search_vector",
            postgresql_using="gin",
        ),
        Index(
            "ix_knowledge_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # 这三个字段共同描述“该切片由哪一套索引规则生成”。检索时必须与知识库
    # 当前配置完全匹配，否则即使向量维度相同也不能安全比较。
    embedding_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"),
        nullable=True,
        comment="生成该切片向量的 AI 模型主键；模型删除后保留切片并置空",
    )
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=KNOWLEDGE_EMBEDDING_DIMENSIONS,
        server_default=text(str(KNOWLEDGE_EMBEDDING_DIMENSIONS)),
        comment="该切片语义向量的实际维度",
    )
    index_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
        comment="切片、清洗和向量生成规则的版本号",
    )

    # metadata 是 Declarative 的保留名称，Python 属性使用 chunk_metadata。
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    # 数据库生成列：插入和更新 content/section_title 时由 PostgreSQL 自动计算。
    # ORM 必须声明 Computed，否则 SQLAlchemy 会显式插入 NULL，触发
    # GeneratedAlwaysError（生成列只允许使用 DEFAULT）。
    search_vector: Mapped[Any | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple'::regconfig, "
            "((COALESCE(section_title, ''::character varying))::text "
            "|| ' '::text) || content)",
            persisted=True,
        ),
        nullable=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(KNOWLEDGE_EMBEDDING_DIMENSIONS),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    document: Mapped[KnowledgeDocument] = relationship(
        "KnowledgeDocument",
        back_populates="chunks",
        foreign_keys=[document_id],
    )
