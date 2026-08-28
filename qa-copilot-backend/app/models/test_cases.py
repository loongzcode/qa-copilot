from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, utc_now

if TYPE_CHECKING:
    from app.models.ai_model import AIModel
    from app.models.prompt_template import PromptTemplate
    from app.models.requirements import Requirement, RequirementItem
    from app.models.test_modules import TestModule
    from app.models.test_projects import TestProjects
    from app.models.user import User


class TestCase(TimestampMixin, Base):
    """人工创建或 AI 生成的结构化测试用例主记录。"""

    __tablename__ = "test_cases"
    __table_args__ = (
        UniqueConstraint("project_id", "case_code", name="uq_test_cases_project_code"),
        CheckConstraint(
            "case_type IN ('FUNCTIONAL', 'API', 'UI', 'PERFORMANCE', 'SECURITY', "
            "'COMPATIBILITY', 'REGRESSION', 'SMOKE', 'OTHER')",
            name="chk_test_cases_type",
        ),
        CheckConstraint("priority IN ('P0', 'P1', 'P2', 'P3')", name="chk_test_cases_priority"),
        CheckConstraint(
            "status IN ('DRAFT', 'REVIEWING', 'APPROVED', 'REJECTED', 'PUBLISHED', 'DISABLED')",
            name="chk_test_cases_status",
        ),
        CheckConstraint("source IN ('MANUAL', 'AI_GENERATED', 'IMPORTED')", name="chk_test_cases_source"),
        CheckConstraint("version > 0", name="chk_test_cases_version"),
        Index("ix_test_cases_project_status", "project_id", "status"),
        Index("ix_test_cases_module_id", "module_id"),
        {"comment": "项目内可版本追踪、可审核发布的测试用例"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="测试用例主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"), nullable=False, comment="所属测试项目 ID"
    )
    module_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_modules.id", ondelete="SET NULL"), nullable=True, comment="可选的所属功能模块 ID"
    )
    case_code: Mapped[str | None] = mapped_column(String(80), nullable=True, comment="项目内可选的用例编码")
    title: Mapped[str] = mapped_column(String(300), nullable=False, comment="测试用例标题")
    case_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="FUNCTIONAL", server_default=text("'FUNCTIONAL'"), comment="测试类型"
    )
    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, default="P2", server_default=text("'P2'"), comment="用例优先级"
    )
    preconditions: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''"), comment="执行用例前必须满足的条件"
    )
    expected_summary: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''"), comment="整条用例的总体预期结果"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default=text("'DRAFT'"), comment="用例审核发布状态"
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MANUAL", server_default=text("'MANUAL'"), comment="用例来源"
    )
    automatable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), comment="是否适合转换为自动化定义"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1"), comment="测试用例版本号"
    )
    case_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="测试用例扩展信息，例如生成配置和业务标签",
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="创建用例的用户 ID"
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="最后编辑用例的用户 ID"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="软删除时间；为空表示用例仍有效"
    )

    project: Mapped[TestProjects] = relationship("TestProjects", lazy="selectin")
    module: Mapped[TestModule | None] = relationship("TestModule", lazy="selectin")
    creator: Mapped[User | None] = relationship("User", foreign_keys=[created_by], lazy="selectin")
    updater: Mapped[User | None] = relationship("User", foreign_keys=[updated_by], lazy="selectin")
    steps: Mapped[list[TestCaseStep]] = relationship(
        "TestCaseStep", back_populates="test_case", cascade="all, delete-orphan", passive_deletes=True
    )


class TestCaseStep(TimestampMixin, Base):
    """测试用例中的一条可排序执行步骤。"""

    __tablename__ = "test_case_steps"
    __table_args__ = (
        UniqueConstraint("test_case_id", "step_no", name="uq_test_case_steps_case_no"),
        CheckConstraint("step_no > 0", name="chk_test_case_steps_no"),
        {"comment": "测试用例的结构化操作步骤和预期结果"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="用例步骤主键")
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, comment="所属测试用例 ID"
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="步骤序号，从 1 开始")
    action: Mapped[str] = mapped_column(Text, nullable=False, comment="本步骤执行的操作")
    test_data: Mapped[Any | None] = mapped_column(
        JSONB, nullable=True, comment="本步骤使用的结构化测试数据"
    )
    expected_result: Mapped[str] = mapped_column(Text, nullable=False, comment="本步骤预期结果")

    test_case: Mapped[TestCase] = relationship("TestCase", back_populates="steps")


class RequirementCaseLink(Base):
    """一个原子需求点与一条测试用例之间的覆盖证据。"""

    __tablename__ = "requirement_case_links"
    __table_args__ = (
        CheckConstraint("coverage_type IN ('FULL', 'PARTIAL')", name="chk_requirement_case_links_coverage"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="chk_requirement_case_links_confidence"),
        Index("ix_requirement_case_links_case_id", "test_case_id"),
        {"comment": "需求点与测试用例的覆盖矩阵；没有记录表示未覆盖"},
    )

    requirement_item_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_items.id", ondelete="CASCADE"), primary_key=True, comment="被覆盖的原子需求点 ID"
    )
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), primary_key=True, comment="提供覆盖的测试用例 ID"
    )
    coverage_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="完全覆盖或部分覆盖")
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, comment="AI 判断覆盖关系的置信度，范围 0 到 1"
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="覆盖判断所依据的步骤、规则和引用快照",
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="建立或确认覆盖关系的用户 ID"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, comment="覆盖关系创建时间"
    )

    requirement_item: Mapped[RequirementItem] = relationship("RequirementItem", lazy="selectin")
    test_case: Mapped[TestCase] = relationship("TestCase", lazy="selectin")
    creator: Mapped[User | None] = relationship("User", lazy="selectin")


class CaseGenerationTask(TimestampMixin, Base):
    """一次覆盖分析和缺失用例生成任务的完整审计记录。"""

    __tablename__ = "case_generation_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'WAITING_REVIEW', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="chk_case_generation_tasks_status",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="chk_case_generation_tasks_progress"),
        Index("ix_case_generation_tasks_project_status", "project_id", "status"),
        Index(
            "uq_case_generation_tasks_active_requirement",
            "requirement_id",
            unique=True,
            postgresql_where=text(
                "status IN ('PENDING', 'RUNNING', 'WAITING_REVIEW')"
            ),
        ),
        {"comment": "覆盖分析和缺失用例生成任务的输入、检索及输出快照"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="生成任务主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"), nullable=False, comment="所属测试项目 ID"
    )
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False, comment="本次分析的需求 ID"
    )
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True, comment="实际使用的生成模型 ID"
    )
    prompt_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True, comment="实际使用的 Prompt 模板 ID"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default=text("'PENDING'"), comment="生成任务状态"
    )
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), comment="提交给工作流的需求和配置快照"
    )
    output_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="模型结构化输出和质量检查结果快照",
    )
    retrieval_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), comment="检索到的历史用例及其分数快照"
    )
    progress: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"), comment="任务进度百分比，范围 0 到 100"
    )
    current_stage: Mapped[str | None] = mapped_column(
        String(80), nullable=True, comment="任务当前执行阶段，供前端展示进度说明"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="任务失败时的脱敏错误摘要")
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="发起生成任务的用户 ID"
    )
    supervisor_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("supervisor_plan_steps.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        comment="由 Supervisor 写能力触发时的步骤 ID；用于重复消息幂等复用同一任务",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="任务开始执行时间"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="任务完成、失败或取消的时间"
    )

    project: Mapped[TestProjects] = relationship("TestProjects", lazy="selectin")
    requirement: Mapped[Requirement] = relationship("Requirement", lazy="selectin")
    model: Mapped[AIModel | None] = relationship("AIModel", lazy="selectin")
    prompt_template: Mapped[PromptTemplate | None] = relationship("PromptTemplate", lazy="selectin")
    requester: Mapped[User | None] = relationship("User", foreign_keys=[requested_by], lazy="selectin")


class CaseReviewRecord(Base):
    """测试人员对 AI 生成用例执行的一次审核动作。"""

    __tablename__ = "case_review_records"
    __table_args__ = (
        CheckConstraint(
            "action IN ('SUBMIT', 'ACCEPT', 'MODIFY', 'REJECT', 'DUPLICATE', 'PUBLISH', 'DISABLE')",
            name="chk_case_review_records_action",
        ),
        Index("ix_case_review_records_case_created", "test_case_id", "created_at"),
        {"comment": "AI 生成用例的接受、修改、驳回、判重和发布审计记录"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="审核记录主键")
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, comment="被审核的测试用例 ID"
    )
    generation_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("case_generation_tasks.id", ondelete="SET NULL"), nullable=True, comment="产生该用例的生成任务 ID"
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="执行审核动作的用户 ID"
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False, comment="本次审核动作")
    comment: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''"), comment="审核意见"
    )
    before_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="审核动作前的用例快照"
    )
    after_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="审核动作后的用例快照"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, comment="审核动作发生时间"
    )

    test_case: Mapped[TestCase] = relationship("TestCase", lazy="selectin")
    generation_task: Mapped[CaseGenerationTask | None] = relationship("CaseGenerationTask", lazy="selectin")
    reviewer: Mapped[User | None] = relationship("User", lazy="selectin")
