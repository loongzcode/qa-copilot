from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.ai_provider import AIProvider


class AIModel(TimestampMixin, Base):
    """具体模型配置实体，一个服务商下的模型标识不能重复。"""

    __tablename__ = "ai_models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", name="uq_provider_model"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("ai_providers.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(100))
    model_id: Mapped[str] = mapped_column(String(160))
    reasoning_effort: Mapped[str | None] = mapped_column(String(20), nullable=True)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    task_types: Mapped[list[str]] = mapped_column(JSON, default=list)

    provider: Mapped[AIProvider] = relationship(back_populates="models")
    # 模型一次请求能够容纳的总 Token，包括 Prompt、历史消息、
    # 知识库上下文、当前问题和模型输出。
    context_window_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=32768,
        server_default=text("32768"),
    )
