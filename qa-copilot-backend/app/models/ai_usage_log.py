from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import AIUsageStatus
from app.core.database import Base
from app.models.mixins import utc_now

if TYPE_CHECKING:
    from app.models.test_projects import TestProjects
    from app.models.user import User


class AIUsageLog(Base):
    """
    保存每一次 AI 模型调用的审计与用量信息。

    日志只记录调用身份、Token、耗时和脱敏后的错误摘要，不保存完整
    Prompt、模型回答、API Key 或 Authorization 等敏感正文。
    """

    __tablename__ = "ai_usage_logs"
    __table_args__ = (
        # 状态只有成功和失败，避免数据库中出现前端无法识别的任意字符串。
        CheckConstraint(
            "status IN ('success', 'failed')",
            name="chk_ai_usage_logs_status",
        ),
        # Token、耗时和命中数量都不应该出现负数。
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 "
            "AND total_tokens >= 0 AND latency_ms >= 0 "
            "AND retrieval_hit_count >= 0",
            name="chk_ai_usage_logs_non_negative_metrics",
        ),
        # 默认列表按时间倒序读取。
        Index("ix_ai_usage_logs_created_at", "created_at"),
        # 以下组合索引用于常用筛选，并继续按时间读取最近记录。
        Index("ix_ai_usage_logs_status_created_at", "status", "created_at"),
        Index(
            "ix_ai_usage_logs_provider_created_at",
            "provider_id",
            "created_at",
        ),
        Index("ix_ai_usage_logs_model_created_at", "model_id", "created_at"),
        Index(
            "ix_ai_usage_logs_task_type_created_at",
            "task_type",
            "created_at",
        ),
        Index("ix_ai_usage_logs_user_created_at", "user_id", "created_at"),
        Index(
            "ix_ai_usage_logs_project_created_at",
            "project_id",
            "created_at",
        ),
        Index(
            "ix_ai_usage_logs_request_id",
            "request_id",
            postgresql_where=text("request_id IS NOT NULL"),
        ),
        Index(
            "ix_ai_usage_logs_task_id",
            "task_id",
            postgresql_where=text("task_id IS NOT NULL"),
        ),
    )

    # 调用日志主键。
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 同一次 HTTP 请求使用相同标识，便于串起完整调用链。
    request_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    # Celery 任务、生成批次或其他业务任务标识。
    task_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    # 发起调用的用户；后台 Worker 没有明确用户时允许为空。
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 当前仍存在的调用用户；用户被删除后关系为空，但日志继续保留。
    user: Mapped[User | None] = relationship(
        foreign_keys=[user_id],
        lazy="selectin",
    )
    # 调用所属项目；模型连接测试等系统级调用允许为空。
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 当前仍存在的所属项目；项目被删除后关系为空。
    project: Mapped[TestProjects | None] = relationship(
        foreign_keys=[project_id],
        lazy="selectin",
    )
    # 服务商配置删除后，数据库自动把外键置空，但不会删除日志。
    provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_providers.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 模型配置删除后，数据库自动把外键置空，但不会删除日志。
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 调用发生时的服务商名称快照，配置删除后仍能显示历史名称。
    provider_name: Mapped[str] = mapped_column(String(100))
    # 调用发生时的平台模型名称快照。
    model_name: Mapped[str] = mapped_column(String(100))
    # 调用用途，例如 embedding、rerank、knowledge_qa 或 query_rewrite。
    task_type: Mapped[str] = mapped_column(String(40))
    # 调用最终状态。
    status: Mapped[str] = mapped_column(
        String(20),
        default=AIUsageStatus.SUCCESS.value,
        server_default=text("'success'"),
    )
    # 发送给模型的输入 Token 数。
    input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
    )
    # 模型生成的输出 Token 数。
    output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
    )
    # 输入和输出的总 Token 数。
    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
    )
    # 从请求模型到收到结果的耗时，单位为毫秒。
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
    )
    # 知识检索最终命中的资料数量；非检索任务保持为 0。
    retrieval_hit_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
    )
    # 调用失败时保存脱敏后的异常摘要，成功时为空。
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 调用发生时间，统一保存带时区时间。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
