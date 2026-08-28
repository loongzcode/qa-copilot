from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    literal,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, query_expression, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.knowledge_documents import KnowledgeDocument
    from app.models.test_modules import TestModule
    from app.models.test_projects import TestProjects
    from app.models.user import User


class Requirement(TimestampMixin, Base):
    """一份可追踪版本、可被 AI 拆解的需求业务记录。"""

    __tablename__ = "requirements"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'EXTRACTING', 'REVIEWING', 'CONFIRMED', 'FAILED', 'ARCHIVED')",
            name="chk_requirements_status",
        ),
        Index("ix_requirements_project_status", "project_id", "status"),
        Index("ix_requirements_module_id", "module_id"),
        {"comment": "项目需求及其版本、来源和拆解状态"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="需求主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属测试项目 ID，是需求数据权限边界",
    )
    module_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_modules.id", ondelete="SET NULL"),
        nullable=True,
        comment="可选的所属功能模块 ID",
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联的原始知识文档 ID，用于读取需求正文和定位证据",
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False, comment="需求标题")
    version: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="1.0",
        server_default=text("'1.0'"),
        comment="需求版本标识，例如 1.0、1.1 或 2026.08",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="DRAFT",
        server_default=text("'DRAFT'"),
        comment="需求状态：草稿、拆解中、待确认、已确认或失败",
    )
    source_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="可选的外部需求来源地址",
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
        comment="需求正文的简要说明或 AI 提取摘要",
    )
    requirement_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="需求扩展信息，使用 JSON 保存不固定的业务字段",
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="创建需求的用户 ID",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="软删除时间；为空表示需求仍有效",
    )

    project: Mapped[TestProjects] = relationship("TestProjects", lazy="selectin")
    module: Mapped[TestModule | None] = relationship("TestModule", lazy="selectin")
    document: Mapped[KnowledgeDocument | None] = relationship("KnowledgeDocument", lazy="selectin")
    creator: Mapped[User | None] = relationship("User", lazy="selectin")
    items: Mapped[list[RequirementItem]] = relationship(
        "RequirementItem",
        back_populates="requirement",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (
            RequirementItem.order_no,
            RequirementItem.id,
        ),
    )

    # 下面两个属性不是真实数据库列，列表查询时通过统计表达式动态填充。
    item_count: Mapped[int] = query_expression(literal(0))
    confirmed_item_count: Mapped[int] = query_expression(literal(0))


class RequirementItem(TimestampMixin, Base):
    """从需求中拆出的、可以独立确认和关联测试用例的原子需求点。"""

    __tablename__ = "requirement_items"
    __table_args__ = (
        UniqueConstraint(
            "requirement_id",
            "item_code",
            name="uq_requirement_items_requirement_code",
        ),
        CheckConstraint(
            "item_type IN ('FUNCTIONAL', 'BUSINESS_RULE', 'NORMAL_FLOW', "
            "'EXCEPTION_FLOW', 'BOUNDARY', 'PERMISSION', 'PERFORMANCE', "
            "'SECURITY', 'COMPATIBILITY', 'OTHER')",
            name="chk_requirement_items_type",
        ),
        CheckConstraint(
            "priority IN ('P0', 'P1', 'P2', 'P3')",
            name="chk_requirement_items_priority",
        ),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="chk_requirement_items_not_self_parent"),
        Index("ix_requirement_items_requirement_parent", "requirement_id", "parent_id"),
        Index("ix_requirement_items_requirement_confirmed", "requirement_id", "confirmed"),
        {"comment": "需求拆解后可人工校正和确认的原子需求点"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="原子需求点主键")
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属需求 ID",
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement_items.id", ondelete="CASCADE"),
        nullable=True,
        comment="可选的父需求点 ID，用于组织层级结构",
    )
    item_code: Mapped[str | None] = mapped_column(
        String(80), nullable=True, comment="需求内可选的需求点编码"
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False, comment="原子需求点标题")
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="原子需求点的完整说明")
    item_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="FUNCTIONAL",
        server_default=text("'FUNCTIONAL'"),
        comment="需求点类型",
    )
    priority: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="P2",
        server_default=text("'P2'"),
        comment="需求点优先级，P0 最高、P3 最低",
    )
    acceptance_criteria: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
        comment="判断该需求点是否实现的验收条件",
    )
    source_locator: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="原文定位信息，例如页码、章节和切片 ID",
    )
    ai_generated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="是否由 AI 自动提取",
    )
    confirmed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="是否已由测试人员人工确认",
    )
    order_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="需求点在同一需求中的显示顺序，数值越小越靠前",
    )

    requirement: Mapped[Requirement] = relationship("Requirement", back_populates="items")
    parent: Mapped[RequirementItem | None] = relationship(
        "RequirementItem",
        back_populates="children",
        remote_side=[id],
    )
    children: Mapped[list[RequirementItem]] = relationship(
        "RequirementItem",
        back_populates="parent",
    )
