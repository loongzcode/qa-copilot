from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.automation_definitions import AutomationDefinition
    from app.models.automation_execution_step_results import AutomationExecutionStepResult
    from app.models.test_environments import TestEnvironment
    from app.models.test_projects import TestProjects
    from app.models.user import User


class AutomationExecutionTask(TimestampMixin, Base):
    """一次已审批自动化定义在指定测试环境中的后台执行任务。

    功能：保存入队快照、状态、进度、超时、取消请求和最小执行结论。
    作用：连接同步提交 API、PostgreSQL 事务性发件箱、Celery Worker 和后续报告。
    为什么用它：长时间 HTTP 测试不能占用 FastAPI 请求；持久化状态使刷新页面、
    Worker 重启和重复消息情况下仍能恢复、查询并进行幂等判断。
    """

    __tablename__ = "automation_execution_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','RUNNING','CANCEL_REQUESTED','PASSED','FAILED','TIMED_OUT','CANCELLED')",
            name="chk_automation_execution_tasks_status",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="chk_automation_execution_tasks_progress"),
        CheckConstraint("timeout_seconds BETWEEN 10 AND 7200", name="chk_automation_execution_tasks_timeout"),
        Index("ix_automation_execution_tasks_project_status", "project_id", "status"),
        Index(
            "uq_automation_execution_tasks_active_definition",
            "definition_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING','RUNNING','CANCEL_REQUESTED')"),
        ),
        {"comment": "受控接口自动化后台执行任务"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="执行任务主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"), nullable=False, comment="所属项目 ID"
    )
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("automation_definitions.id", ondelete="RESTRICT"), nullable=False, comment="执行的已审批定义 ID"
    )
    environment_id: Mapped[int] = mapped_column(
        ForeignKey("test_environments.id", ondelete="RESTRICT"), nullable=False, comment="目标测试环境 ID"
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING", server_default=text("'PENDING'"), comment="任务执行状态"
    )
    progress: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"), comment="任务进度百分比"
    )
    current_stage: Mapped[str] = mapped_column(
        String(80), nullable=False, default="QUEUED", server_default=text("'QUEUED'"), comment="当前执行阶段"
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, comment="整次任务总超时秒数")
    celery_task_id: Mapped[str | None] = mapped_column(String(80), nullable=True, comment="Celery Broker 任务 ID")
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="提交时自动化定义内容摘要")
    environment_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="提交时测试环境更新时间，用于阻止配置漂移"
    )
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="最小执行结论；详细步骤报告由 FR-AUTO-003 扩展",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败时的脱敏错误摘要")
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="发起任务的用户 ID"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="开始执行时间")
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="进入最终状态时间"
    )

    project: Mapped[TestProjects] = relationship("TestProjects", lazy="selectin")
    definition: Mapped[AutomationDefinition] = relationship("AutomationDefinition", lazy="selectin")
    environment: Mapped[TestEnvironment] = relationship("TestEnvironment", lazy="selectin")
    requester: Mapped[User | None] = relationship("User", lazy="selectin")
    step_results: Mapped[list[AutomationExecutionStepResult]] = relationship(
        "AutomationExecutionStepResult",
        back_populates="execution_task",
        cascade="all, delete-orphan",
        order_by="AutomationExecutionStepResult.step_no",
        lazy="raise",
    )
