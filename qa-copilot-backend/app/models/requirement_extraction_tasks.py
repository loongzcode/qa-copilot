from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.ai_model import AIModel
    from app.models.prompt_template import PromptTemplate
    from app.models.requirements import Requirement
    from app.models.test_projects import TestProjects
    from app.models.user import User


class RequirementExtractionTask(TimestampMixin, Base):
    """一次 AI 需求拆解的进度、输入输出和失败信息。

    Requirement 只保存当前业务状态；本表则保留每一次拆解尝试。这样即使重试
    多次，也能查到每次用了哪个模型、在哪一步失败以及模型曾返回什么结果。
    """

    __tablename__ = "requirement_extraction_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="chk_requirement_extraction_tasks_status",
        ),
        CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="chk_requirement_extraction_tasks_progress",
        ),
        Index(
            "ix_requirement_extraction_tasks_project_status",
            "project_id",
            "status",
        ),
        Index(
            "ix_requirement_extraction_tasks_requirement_created",
            "requirement_id",
            "created_at",
        ),
        # 数据库最终兜底：同一个需求不能同时存在两个排队中或运行中的任务。
        Index(
            "uq_requirement_extraction_tasks_active_requirement",
            "requirement_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'RUNNING')"),
        ),
        {"comment": "AI 需求拆解任务的执行进度、输入输出快照和失败审计"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="需求拆解任务主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属测试项目 ID，也是任务的数据权限边界",
    )
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        comment="本次需要拆解的需求 ID",
    )
    celery_task_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="Celery 任务 ID，用于关联消息队列中的实际任务",
    )
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"),
        nullable=True,
        comment="本次实际调用的 AI 模型 ID",
    )
    prompt_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"),
        nullable=True,
        comment="本次实际使用的需求拆解 Prompt 模板 ID",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
        comment="任务状态：排队中、执行中、成功、失败或已取消",
    )
    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="任务完成百分比，范围为 0 到 100",
    )
    current_stage: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="QUEUED",
        server_default=text("'QUEUED'"),
        comment="当前业务阶段，例如读取文档、调用模型或保存需求点",
    )
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="任务提交时的需求版本、文档和执行参数快照",
    )
    output_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="模型原始结构化结果和最终保存数量等输出快照",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="任务失败时经过脱敏和截断的错误摘要",
    )
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="发起本次需求拆解的用户 ID",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Worker 真正开始执行任务的时间",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="任务成功、失败或取消的结束时间",
    )

    project: Mapped[TestProjects] = relationship("TestProjects", lazy="selectin")
    requirement: Mapped[Requirement] = relationship("Requirement", lazy="selectin")
    model: Mapped[AIModel | None] = relationship("AIModel", lazy="selectin")
    prompt_template: Mapped[PromptTemplate | None] = relationship("PromptTemplate", lazy="selectin")
    requester: Mapped[User | None] = relationship("User", foreign_keys=[requested_by], lazy="selectin")
