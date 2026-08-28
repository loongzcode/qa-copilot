"""通知渠道管理接口返回的数据结构。"""

from datetime import datetime
from typing import Any

from app.core.constants import NotificationChannelType
from app.schemas.camel_model import CamelModel


class NotificationChannelVO(CamelModel):
    """通知渠道安全视图；只说明密钥是否存在，不返回密钥内容。"""

    id: int
    name: str
    channel_type: NotificationChannelType
    config: dict[str, Any]
    secret_configured: bool
    enabled: bool
    importance_threshold: int
    breaking_only: bool
    created_at: datetime
    updated_at: datetime


class NotificationChannelTestResultVO(CamelModel):
    """发送测试消息后的结果和耗时。"""

    success: bool
    message: str
    latency_ms: int

