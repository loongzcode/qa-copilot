from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, utc_now


class OutboxEvent(TimestampMixin, Base):
    """等待可靠发布到消息队列的业务事件。

    功能：在 PostgreSQL 中持久化需要发送给 Celery 的任务消息、重试次数和
    发布结果。

    作用：业务 Service 可以在修改业务数据的同一个数据库事务中新增本记录；
    独立发布器随后认领记录并把消息发送到 Redis。即使应用在提交事务后崩溃，
    未发布事件也不会丢失。

    为什么用它：PostgreSQL 事务无法直接控制 Redis。事务性发件箱把“需要发
    消息”先变成数据库数据，从而利用数据库事务的原子性；代价是消息采用
    至少一次投递，消费者仍然必须具备幂等性。
    """

    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'RETRY', 'PUBLISHED', 'FAILED')",
            name="chk_outbox_events_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0",
            name="chk_outbox_events_attempts",
        ),
        # 发布器最常使用 status + available_at 查询下一批可发送事件。
        Index(
            "ix_outbox_events_dispatch",
            "status",
            "available_at",
            "id",
        ),
        # 同一业务对象同一时间只允许有一条活动事件，防止用户连续点击时
        # 重复创建尚未处理的索引任务。历史 PUBLISHED/FAILED 记录仍会保留。
        Index(
            "uq_outbox_events_active_aggregate",
            "event_type",
            "aggregate_type",
            "aggregate_id",
            unique=True,
            postgresql_where=text(
                "status IN ('PENDING', 'PROCESSING', 'RETRY')"
            ),
        ),
        {"comment": "需要可靠发布到 Celery 的事务性发件箱事件"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="发件箱事件主键，也可作为消息幂等标识",
    )
    event_type: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        comment="事件类型，发布器据此选择要调用的 Celery 任务",
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        comment="产生事件的业务对象类型，例如 KNOWLEDGE_DOCUMENT",
    )
    aggregate_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="产生事件的业务对象 ID；故意不设外键以保留消息审计记录",
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="发布消息所需的参数快照，不依赖业务表的后续变化",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
        comment="PENDING/PROCESSING/RETRY/PUBLISHED/FAILED",
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="已经尝试发布到 Redis 的次数",
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default=text("10"),
        comment="允许发布的最大尝试次数，达到后转为 FAILED",
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="下次允许发布的时间，用于失败后的延迟重试",
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="发布器认领事件的时间，用于恢复超时的 PROCESSING 事件",
    )
    locked_by: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        comment="认领事件的发布器实例标识，便于排查并发发布问题",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="消息成功写入 Redis 的时间",
    )
    broker_task_id: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        comment="发送给 Celery 的任务 ID，用于关联队列日志并追踪重复投递",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="最近一次发布失败的脱敏错误摘要",
    )
