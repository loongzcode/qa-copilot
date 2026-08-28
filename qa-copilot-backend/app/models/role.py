from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.associations import role_menu_table, user_role_table
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.menu import Menu
    from app.models.user import User


class Role(TimestampMixin, Base):
    """角色实体，通过菜单树同时关联页面权限和按钮权限。"""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    users: Mapped[list[User]] = relationship(
        secondary=user_role_table,
        back_populates="roles",
        lazy="selectin",
    )
    menus: Mapped[list[Menu]] = relationship(
        secondary=role_menu_table,
        back_populates="roles",
        lazy="selectin",
    )
