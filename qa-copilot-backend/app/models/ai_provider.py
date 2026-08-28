from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.ai_model import AIModel


class AIProvider(TimestampMixin, Base):
    """AI 服务商配置实体，密钥只保存加密后的内容。"""

    __tablename__ = "ai_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    provider_type: Mapped[str] = mapped_column(String(40), default="openai_responses")
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    encrypted_api_key: Mapped[str] = mapped_column(Text, default="")
    custom_headers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    models: Mapped[list[AIModel]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
