from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def utc_now() -> datetime:
    """统一使用 UTC 保存时间，展示时再由前端转换成用户所在时区。"""

    return datetime.now(UTC)


class TimestampMixin:
    """为需要创建时间和更新时间的实体提供公共字段。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        comment="更新时间",
    )
