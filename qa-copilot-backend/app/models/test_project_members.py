from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import utc_now

if TYPE_CHECKING:
    from app.models.test_projects import TestProjects
    from app.models.user import User


class TestProjectMember(Base):
    """项目与用户的成员关系。"""

    __tablename__ = "test_project_members"

    __table_args__ = (
        CheckConstraint(
            "member_role IN ('OWNER', 'MANAGER', 'MEMBER', 'VIEWER')",
            name="chk_test_project_members_role",
        ),
        Index("ix_test_project_members_user_id", "user_id"),
    )

    # 两个字段共同组成联合主键，保证同一用户不会被重复加入同一项目。
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    member_role: Mapped[str] = mapped_column(
        String(20),
        default="MEMBER",
        server_default="MEMBER",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )

    project: Mapped[TestProjects] = relationship(
        "TestProjects",
        foreign_keys=[project_id],
        lazy="selectin",
    )
    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[user_id],
        lazy="selectin",
    )
