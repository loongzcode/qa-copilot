from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    literal,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, query_expression, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.knowledge_bases import KnowledgeBase
    from app.models.knowledge_document_chunks import KnowledgeDocumentChunk
    from app.models.test_modules import TestModule
    from app.models.user import User


class KnowledgeDocument(TimestampMixin, Base):
    """知识库中的原始文档及其解析状态。

    数据库只保存文件元数据和对象存储位置，文件二进制内容不写入 PostgreSQL。
    文本切片和向量由 knowledge_document_chunks 表单独保存。
    """

    __tablename__ = "knowledge_documents"

    __table_args__ = (
        CheckConstraint(
            "document_type IN ('STANDARD_CASE', 'TEST_PROCESS', "
            "'OPERATION_GUIDE', 'SYSTEM_DESIGN', 'REQUIREMENT', "
            "'API_DOCUMENT', 'DEFECT_EXPERIENCE', 'OTHER')",
            name="chk_knowledge_documents_type",
        ),
        CheckConstraint(
            "source_type IN ('UPLOAD', 'URL', 'MANUAL', 'IMPORT')",
            name="chk_knowledge_documents_source",
        ),
        CheckConstraint(
            "parse_status IN ('PENDING', 'PARSING', 'INDEXING', 'READY', 'FAILED')",
            name="chk_knowledge_documents_status",
        ),
        CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="chk_knowledge_documents_size",
        ),
        CheckConstraint("version > 0", name="chk_knowledge_documents_version"),
        Index(
            "ix_knowledge_documents_base_status",
            "knowledge_base_id",
            "parse_status",
        ),
        Index("ix_knowledge_documents_module", "module_id"),
        Index("ix_knowledge_documents_sha256", "sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    module_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_modules.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="UPLOAD",
        server_default=text("'UPLOAD'"),
    )
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    object_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    parse_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    index_task_id: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        comment="最近一次实际执行索引的 Celery 任务 ID",
    )
    index_queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="用户提交索引请求并登记发件箱事件的时间；为空表示只上传未提交",
    )
    index_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最近一次索引 Worker 成功认领文档的时间",
    )
    index_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="索引 Worker 最近一次报告仍在正常处理的时间",
    )
    index_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最近一次索引成功或最终失败的结束时间",
    )
    index_recovery_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="被补偿扫描重新投递的次数，用于阻止无限恢复",
    )

    # metadata 是 SQLAlchemy Declarative 的保留属性，因此 Python 中换一个名字，
    # mapped_column("metadata", ...) 仍然映射数据库里的 metadata 字段。
    document_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    knowledge_base: Mapped[KnowledgeBase] = relationship(
        "KnowledgeBase",
        foreign_keys=[knowledge_base_id],
        lazy="selectin",
    )
    module: Mapped[TestModule | None] = relationship(
        "TestModule",
        foreign_keys=[module_id],
        lazy="selectin",
    )
    creator: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="selectin",
    )
    chunks: Mapped[list[KnowledgeDocumentChunk]] = relationship(
        "KnowledgeDocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # 不是 knowledge_documents 的真实字段，由列表查询统计切片数量后动态填充。
    chunk_count: Mapped[int] = query_expression(literal(0))
