from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.test_cases import TestCase
    from app.models.test_projects import TestProjects
    from app.models.user import User


class AutomationDefinition(TimestampMixin, Base):
    """由已发布接口用例转换出的、经过白名单约束的自动化测试定义。

    功能：保存可审计、可版本化的 JSON 测试步骤，而不是保存可直接执行的代码。
    作用：位于人工测试用例和后续自动化执行器之间；执行器只允许读取已审批版本。
    为什么用它：模型或用户提供的任意代码存在命令执行风险，固定 JSON 协议能够在
    真正发请求前完成结构、权限和安全校验，也便于版本比较和跨执行器复用。
    """

    __tablename__ = "automation_definitions"
    __table_args__ = (
        UniqueConstraint(
            "test_case_id",
            "version",
            name="uq_automation_definitions_case_version",
        ),
        CheckConstraint("version > 0", name="chk_automation_definitions_version"),
        CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'RETIRED')",
            name="chk_automation_definitions_status",
        ),
        Index(
            "uq_automation_definitions_approved_case",
            "test_case_id",
            unique=True,
            postgresql_where=text("status = 'APPROVED' AND deleted_at IS NULL"),
        ),
        Index(
            "ix_automation_definitions_project_status",
            "project_id",
            "status",
        ),
        {"comment": "受控 JSON 接口自动化定义及其审批版本"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="自动化定义主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属测试项目 ID，用于项目数据权限隔离",
    )
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        nullable=False,
        comment="来源测试用例 ID",
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False, comment="自动化定义名称")
    version: Mapped[int] = mapped_column(Integer, nullable=False, comment="同一用例下递增的定义版本")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="DRAFT",
        server_default=text("'DRAFT'"),
        comment="定义状态：草稿、已审批或已退出使用",
    )
    schema_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="1.0", server_default=text("'1.0'"), comment="受控 JSON 协议版本"
    )
    source_case_version: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="生成定义时来源测试用例的版本快照"
    )
    definition: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, comment="已通过白名单校验的自动化步骤 JSON"
    )
    definition_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="规范化 JSON 的 SHA-256 摘要，用于识别内容变化"
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="创建定义的用户 ID"
    )
    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="审批该版本的用户 ID"
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="定义通过审批的时间"
    )
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="定义退出使用的时间"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="软删除时间；为空表示仍有效"
    )

    project: Mapped[TestProjects] = relationship("TestProjects", lazy="selectin")
    test_case: Mapped[TestCase] = relationship("TestCase", lazy="selectin")
    creator: Mapped[User | None] = relationship("User", foreign_keys=[created_by], lazy="selectin")
    approver: Mapped[User | None] = relationship("User", foreign_keys=[approved_by], lazy="selectin")


class AutomationDefinitionChange(TimestampMixin, Base):
    """自动化定义的不可变变更快照。

    功能：保存每次创建、编辑、审批、退出和删除前后的关键内容。
    作用：与定义业务操作在同一个 PostgreSQL 事务中写入，组成完整审计链。
    为什么用它：定义主表只保存当前状态，无法还原草稿被反复编辑的过程；独立
    追加表不会覆盖历史，也比只记录文字日志更容易做结构化差异展示。
    """

    __tablename__ = "automation_definition_changes"
    __table_args__ = (
        CheckConstraint(
            "action IN ('CREATED','UPDATED','APPROVED','RETIRED','DELETED')",
            name="chk_automation_definition_changes_action",
        ),
        Index("ix_automation_definition_changes_definition", "definition_id", "id"),
        Index("ix_automation_definition_changes_project", "project_id", "id"),
        {"comment": "自动化定义不可变变更快照与审计链"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="变更记录主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"), nullable=False, comment="所属项目 ID"
    )
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, comment="来源测试用例 ID"
    )
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("automation_definitions.id", ondelete="CASCADE"), nullable=False, comment="被修改的定义 ID"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, comment="发生变更时的定义版本")
    action: Mapped[str] = mapped_column(String(20), nullable=False, comment="变更动作")
    before_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, comment="变更前快照")
    after_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, comment="变更后快照")
    changed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="执行变更的用户 ID"
    )

    changer: Mapped[User | None] = relationship("User", foreign_keys=[changed_by], lazy="selectin")
