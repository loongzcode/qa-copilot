from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import KNOWLEDGE_EMBEDDING_DIMENSIONS
from app.core.database import Base
from app.models.mixins import utc_now


class KnowledgeDocumentChunkStaging(Base):
    """尚未发布的知识切片暂存记录。

    功能：分批保存当前索引任务已经完成向量化的切片。
    作用：任务全部成功后，Repository 在单个数据库事务中把这些记录发布到正式
    ``knowledge_document_chunks`` 表；失败时只删除当前任务的暂存数据。
    为什么用它：如果逐批直接写正式表，后续批次失败会留下残缺索引；如果把
    所有批次留在 Python 列表中，则超大文档会占满 Worker 内存。数据库暂存兼顾
    有界内存和原子发布，代价是索引期间需要额外磁盘空间。
    """

    __tablename__ = "knowledge_document_chunk_staging"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "task_id",
            "chunk_index",
            name="uq_knowledge_chunk_staging_task_index",
        ),
        Index(
            "ix_knowledge_chunk_staging_document_task",
            "document_id",
            "task_id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属知识文档 ID",
    )
    task_id: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        comment="生成该批暂存切片的 Celery 任务 ID，也是旧任务写入栅栏",
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    embedding_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"),
        nullable=True,
    )
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    index_version: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    embedding: Mapped[list[float]] = mapped_column(
        Vector(KNOWLEDGE_EMBEDDING_DIMENSIONS),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
