"""Supervisor Agent 目标运行与计划步骤实体。"""

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.ai_model import AIModel
    from app.models.test_projects import TestProjects
    from app.models.tool_center import ToolTask
    from app.models.user import User


class SupervisorSession(TimestampMixin, Base):
    """Supervisor 的持久化聊天会话。

    功能：把同一轮连续交流产生的多次 SupervisorRun 归为一组。
    作用：前端用它恢复会话列表；每个 Run 仍负责可靠执行和审计。
    为什么用它：聊天负责交互、Run 负责执行，避免把审批和步骤状态塞进普通消息文本。
    """

    __tablename__ = "supervisor_sessions"
    __table_args__ = (
        Index("ix_supervisor_sessions_project_user_updated", "project_id", "created_by", "updated_at"),
        {"comment": "Supervisor 聊天会话；一次会话可包含多次受控运行"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="会话主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"), nullable=False, comment="所属项目 ID"
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False, comment="会话标题")
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="会话创建人 ID"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="软删除时间")

    project: Mapped[TestProjects] = relationship("TestProjects", lazy="selectin")
    creator: Mapped[User | None] = relationship("User", foreign_keys=[created_by], lazy="selectin")
    runs: Mapped[list[SupervisorRun]] = relationship(
        "SupervisorRun", back_populates="session", order_by="SupervisorRun.created_at", lazy="raise"
    )


class SupervisorRun(TimestampMixin, Base):
    """一次用户开放目标的完整 Supervisor 运行记录。

    功能：保存目标、规划状态、权限快照、上下文、最终结论和失败信息。
    作用：作为一组 SupervisorPlanStep 的父记录，让页面刷新、服务重启和审计查询
    都能恢复同一次运行，而不是依赖 Python 内存。
    为什么用它：目标级信息与步骤级信息分表保存，可以分页查询运行列表，同时只在查看详情时
    加载步骤；相比把整个计划塞进一个 JSON 字段，更容易按状态查找卡住的任务和建立索引。
    """

    __tablename__ = "supervisor_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PLANNING','PLAN_REJECTED','READY','WAITING_APPROVAL','RUNNING',"
            "'SUCCEEDED','FAILED','CANCELLED')",
            name="chk_supervisor_runs_status",
        ),
        CheckConstraint("invocation_source IN ('SUPERVISOR','MCP')", name="chk_supervisor_runs_source"),
        CheckConstraint("current_step_no >= 0", name="chk_supervisor_runs_current_step"),
        Index("ix_supervisor_runs_project_status", "project_id", "status", "id"),
        Index("ix_supervisor_runs_requester_created", "requested_by", "created_at"),
        {"comment": "Supervisor 开放目标、规划状态和执行结果主记录"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Supervisor 运行主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属项目 ID，也是数据权限隔离边界",
    )
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("supervisor_sessions.id", ondelete="CASCADE"), nullable=True, comment="所属聊天会话 ID"
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False, comment="用户提交的原始目标")
    invocation_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SUPERVISOR", server_default=text("'SUPERVISOR'"), comment="调用来源"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PLANNING", server_default=text("'PLANNING'"), comment="运行状态"
    )
    current_step_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"), comment="当前处理到的步骤序号；0 表示尚未执行"
    )
    plan_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1"), comment="计划版本；重新规划时递增"
    )
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True, comment="生成本次计划的模型 ID"
    )
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="目标发起用户 ID"
    )
    permission_snapshot: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
        comment="规划时用户拥有的权限码快照；执行前仍需重新校验实时权限",
    )
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="规划所依据的业务对象 ID 和脱敏上下文，不保存密钥",
    )
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="运行完成后的结构化结果摘要",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败时的脱敏错误摘要")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="开始执行时间")
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="进入最终状态时间"
    )
    execution_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="执行 Worker 最近一次推进步骤的时间，用于识别失联任务"
    )
    execution_recovery_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"), comment="执行任务因 Worker 失联而重新入队的次数"
    )

    project: Mapped[TestProjects] = relationship("TestProjects", lazy="selectin")
    session: Mapped[SupervisorSession | None] = relationship(
        "SupervisorSession", back_populates="runs", lazy="selectin"
    )
    model: Mapped[AIModel | None] = relationship("AIModel", lazy="selectin")
    requester: Mapped[User | None] = relationship("User", foreign_keys=[requested_by], lazy="selectin")
    steps: Mapped[list[SupervisorPlanStep]] = relationship(
        "SupervisorPlanStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="SupervisorPlanStep.step_no",
        lazy="raise",
    )


class SupervisorPlanStep(TimestampMixin, Base):
    """Supervisor 计划中的一个可独立审批、执行和审计的步骤。

    功能：冻结能力编码、参数、权限、风险、依赖关系、执行状态和结果。
    作用：把模型提出的候选步骤转换成数据库中的受控工作项；后续执行器只读取这些已校验记录。
    为什么用它：每一步独立存储后，可以安全暂停在人工审批处、失败后定位具体步骤，
    也能把高风险步骤关联到现有 ToolTask 审批记录，而不让 Supervisor 自己实现另一套审批。
    """

    __tablename__ = "supervisor_plan_steps"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('READY','BLOCKED_APPROVAL','REJECTED')",
            name="chk_supervisor_plan_steps_decision",
        ),
        CheckConstraint(
            "status IN ('PROPOSED','REJECTED','READY','WAITING_APPROVAL','RUNNING',"
            "'SUCCEEDED','FAILED','SKIPPED','CANCELLED')",
            name="chk_supervisor_plan_steps_status",
        ),
        CheckConstraint("risk_level IN ('LOW','MEDIUM','HIGH')", name="chk_supervisor_plan_steps_risk"),
        CheckConstraint("step_no > 0", name="chk_supervisor_plan_steps_no"),
        UniqueConstraint("run_id", "step_no", name="uq_supervisor_plan_steps_run_no"),
        UniqueConstraint("run_id", "step_key", name="uq_supervisor_plan_steps_run_key"),
        Index("ix_supervisor_plan_steps_run_status", "run_id", "status", "step_no"),
        {"comment": "Supervisor 计划中可独立审批和执行的步骤"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="计划步骤主键")
    run_id: Mapped[int] = mapped_column(
        ForeignKey("supervisor_runs.id", ondelete="CASCADE"), nullable=False, comment="所属 Supervisor 运行 ID"
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="从 1 开始的稳定执行顺序")
    step_key: Mapped[str] = mapped_column(String(64), nullable=False, comment="计划内唯一的步骤标识")
    capability_code: Mapped[str] = mapped_column(String(120), nullable=False, comment="能力目录中的稳定编码")
    purpose: Mapped[str] = mapped_column(Text, nullable=False, comment="模型说明的本步骤目的")
    arguments_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), comment="校验后的脱敏调用参数快照"
    )
    depends_on: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"), comment="必须先成功的步骤标识列表"
    )
    required_permission: Mapped[str] = mapped_column(String(120), nullable=False, comment="规划时冻结的所需权限码")
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, comment="规划时冻结的能力风险等级")
    decision: Mapped[str] = mapped_column(String(30), nullable=False, comment="计划校验器作出的处理决定")
    requires_human_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), comment="执行前是否必须人工审批"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PROPOSED", server_default=text("'PROPOSED'"), comment="步骤执行状态"
    )
    tool_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tool_tasks.id", ondelete="SET NULL"),
        nullable=True,
        comment="中高风险步骤对应的现有工具任务审批记录 ID",
    )
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="执行成功后的结构化结果摘要",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="校验或执行失败的脱敏原因")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="步骤开始执行时间"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="步骤进入最终状态时间"
    )
    approval_decided_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="批准或驳回该步骤的用户 ID"
    )
    approval_decision: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="人工审批决定：APPROVED 或 REJECTED"
    )
    approval_comment: Mapped[str | None] = mapped_column(Text, nullable=True, comment="审批意见")
    approval_decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="人工作出审批决定的时间"
    )

    run: Mapped[SupervisorRun] = relationship("SupervisorRun", back_populates="steps", lazy="selectin")
    tool_task: Mapped[ToolTask | None] = relationship("ToolTask", lazy="selectin")
    approval_decider: Mapped[User | None] = relationship(
        "User", foreign_keys=[approval_decided_by], lazy="selectin"
    )
