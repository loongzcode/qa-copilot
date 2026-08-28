"""自动化定时回归计划实体。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class AutomationSchedule(TimestampMixin, Base):
    """按 Cron 表达式周期提交现有自动化定义。

    功能：保存项目、已审批定义、测试环境和下次触发时间。
    作用：Celery Beat 周期扫描到期记录，再复用既有执行任务与事务性发件箱。
    为什么用它：调度器只负责“何时提交”，不复制执行逻辑；即使调度器重启，
    下次运行时间仍在 PostgreSQL 中，不会因内存状态丢失。
    """

    __tablename__ = "automation_schedules"
    __table_args__ = (
        CheckConstraint("length(cron_expression) BETWEEN 5 AND 120", name="chk_automation_schedules_cron"),
        Index("ix_automation_schedules_due", "enabled", "next_run_at", "id"),
        {"comment": "接口自动化定时回归计划"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="计划主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"), nullable=False, comment="所属项目"
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False, comment="计划名称")
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("automation_definitions.id", ondelete="RESTRICT"), nullable=False, comment="要执行的定义版本"
    )
    environment_id: Mapped[int] = mapped_column(
        ForeignKey("test_environments.id", ondelete="RESTRICT"), nullable=False, comment="非生产测试环境"
    )
    cron_expression: Mapped[str] = mapped_column(String(120), nullable=False, comment="五段 Cron 周期表达式")
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Shanghai", server_default=text("'Asia/Shanghai'"), comment="计划时区"
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300, server_default=text("300"), comment="单次执行总超时秒数"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), comment="是否参与到期扫描"
    )
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="下次触发时间")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="最近触发时间")
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="创建用户"
    )

    definition = relationship("AutomationDefinition", lazy="selectin")
    environment = relationship("TestEnvironment", lazy="selectin")
