from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.test_projects import TestProjects
    from app.models.user import User


class TestEnvironment(TimestampMixin, Base):
    """项目测试环境。

    headers 只保存普通请求头或变量占位符；真正的账号、令牌等变量会先整体
    加密，再写入 encrypted_variables，避免敏感值以明文形式落库。
    """

    __tablename__ = "test_environments"

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "name",
            name="uq_test_environments_project_name",
        ),
        CheckConstraint(
            "length(btrim(base_url)) > 0",
            name="chk_test_environments_base_url",
        ),
        Index(
            "ix_test_environments_project_enabled",
            "project_id",
            "enabled",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    environment_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="TEST",
        server_default=text("'TEST'"),
        comment="环境用途；PRODUCTION 禁止自动化执行",
    )
    base_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    allowed_hosts: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    headers: Mapped[dict[str, str]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    encrypted_variables: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    project: Mapped[TestProjects] = relationship(
        "TestProjects",
        foreign_keys=[project_id],
        lazy="selectin",
    )
    creator: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="selectin",
    )
