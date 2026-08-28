"""通知渠道管理接口接收的数据结构。"""

from typing import Any

from pydantic import Field, field_validator

from app.core.constants import NotificationChannelType
from app.schemas.camel_model import CamelModel


class NotificationChannelBaseDTO(CamelModel):
    """创建和完整编辑通知渠道时共用的非敏感字段。"""

    name: str = Field(min_length=1, max_length=100)
    channel_type: NotificationChannelType
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    importance_threshold: int = Field(default=80, ge=0, le=100)
    breaking_only: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """去掉名称两端空白，拒绝只有空格的渠道名称。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("通知渠道名称不能为空")
        return normalized


class NotificationChannelCreateDTO(NotificationChannelBaseDTO):
    """创建通知渠道；secret 会加密保存且永不通过查询接口返回。"""

    secret: str = Field(min_length=1, max_length=4000)


class NotificationChannelUpdateDTO(CamelModel):
    """部分更新通知渠道；不传 secret 表示继续使用原密钥。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    channel_type: NotificationChannelType | None = None
    config: dict[str, Any] | None = None
    secret: str | None = Field(default=None, min_length=1, max_length=4000)
    enabled: bool | None = None
    importance_threshold: int | None = Field(default=None, ge=0, le=100)
    breaking_only: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_optional_name(cls, value: str | None) -> str | None:
        """更新时只在确实传入名称后执行空白归一化。"""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("通知渠道名称不能为空")
        return normalized

