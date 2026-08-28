from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import NotificationChannelType
from app.core.database import Base
from app.models.mixins import TimestampMixin


class NotificationChannel(TimestampMixin, Base):
    """平台统一维护的自动化结果与系统告警通知渠道。

    config 只保存地址之外的非敏感配置，访问令牌、签名密钥或邮箱密码必须
    加密后写入 encrypted_secret。发送服务只读取已启用渠道，不允许业务
    Worker 直接保存或记录通知密钥。
    """

    __tablename__ = "notification_channels"

    __table_args__ = (
        CheckConstraint(
            "channel_type IN ('WEBHOOK', 'WECHAT_WORK_BOT', 'DINGTALK_BOT', 'SMTP')",
            name="chk_notification_channels_type",
        ),
        CheckConstraint(
            "importance_threshold BETWEEN 0 AND 100",
            name="chk_notification_channels_importance_threshold",
        ),
        {"comment": "平台统一维护的自动化结果与系统告警通知渠道"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="通知渠道主键")
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="通知渠道名称，供管理员和业务规则选择",
    )
    channel_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        default=NotificationChannelType.WEBHOOK.value,
        server_default=text(f"'{NotificationChannelType.WEBHOOK.value}'"),
        comment="渠道类型：通用 Webhook、企业微信、钉钉或 SMTP 邮件",
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="不含密钥的渠道配置，例如接收人、主题前缀和请求超时",
    )
    encrypted_secret: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
        comment="使用 DATA_ENCRYPTION_KEY 加密后的地址、令牌或邮箱密码",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="是否允许业务任务使用该通知渠道",
    )
    importance_threshold: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=80,
        server_default=text("80"),
        comment="最低通知重要度，0 到 100；低于该值的事件不发送",
    )
    breaking_only: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="是否只发送阻断性失败或重要告警",
    )
