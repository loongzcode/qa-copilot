from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    literal,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, query_expression, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin
from app.models.user import User


class TestProjects(TimestampMixin, Base):
    __tablename__ = "test_projects"

    __table_args__ = (
        UniqueConstraint("code", name="uq_test_projects_code"),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')",
            name="chk_test_projects_status",
        ),
        Index("ix_test_projects_owner_id", "owner_id"),
        Index("ix_test_projects_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(
        Text,
        default="",
        server_default=text("''"),
    )
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    owner: Mapped[User | None] = relationship(
        foreign_keys=[owner_id],
        lazy="selectin",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="DRAFT",
        server_default="DRAFT",
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # 这两个属性不是 test_projects 的真实列，由项目列表查询动态填充。
    member_count: Mapped[int] = query_expression(literal(0))
    module_count: Mapped[int] = query_expression(literal(0))
