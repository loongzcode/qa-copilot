"""自动化任务的逐步骤脱敏结果。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.automation_execution_tasks import AutomationExecutionTask


class AutomationExecutionStepResult(TimestampMixin, Base):
    """保存一次执行中单个 HTTP 步骤的脱敏报告。

    功能：记录步骤状态、耗时、请求/响应摘要、断言结果和安全错误信息。
    作用：任务表保存整体结论，本表为报告详情提供有序步骤；任务删除时级联清理。
    为什么用它：步骤是可增长的一对多数据，独立表比把全部详情塞进任务 JSONB
    更适合分页、统计和后续趋势分析；摘要只保留结构信息，避免凭据和正文落库。
    """

    __tablename__ = "automation_execution_step_results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PASSED','FAILED','SKIPPED')",
            name="chk_automation_execution_step_results_status",
        ),
        CheckConstraint("step_no > 0", name="chk_automation_execution_step_results_step_no"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="chk_automation_step_duration"),
        UniqueConstraint("execution_task_id", "step_no", name="uq_automation_execution_step_task_no"),
        Index("ix_automation_execution_step_results_task", "execution_task_id", "step_no"),
        {"comment": "自动化执行任务的逐步骤脱敏结果"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="步骤结果主键")
    execution_task_id: Mapped[int] = mapped_column(
        ForeignKey("automation_execution_tasks.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属自动化执行任务 ID",
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="步骤顺序号，从 1 开始")
    name: Mapped[str] = mapped_column(String(300), nullable=False, comment="执行时的步骤名称快照")
    status: Mapped[str] = mapped_column(String(16), nullable=False, comment="PASSED/FAILED/SKIPPED")
    method: Mapped[str] = mapped_column(String(10), nullable=False, comment="HTTP 方法")
    path: Mapped[str] = mapped_column(String(2000), nullable=False, comment="不包含主机的相对请求路径")
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="HTTP 响应状态码")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="步骤耗时毫秒数")
    request_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="请求结构摘要，只保存参数名、请求头名和正文类型",
    )
    response_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="响应摘要，只保存状态码、类型和字节数，不保存正文",
    )
    assertions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
        comment="断言类型、表达式及通过状态，不保存敏感实际值",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="步骤失败的脱敏原因")

    execution_task: Mapped[AutomationExecutionTask] = relationship(
        "AutomationExecutionTask",
        back_populates="step_results",
    )
