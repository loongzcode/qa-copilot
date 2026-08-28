from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.associations import role_menu_table
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.role import Role


class Menu(TimestampMixin, Base):
    """目录、页面和按钮权限共用的菜单树实体。"""

    __tablename__ = "menus"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("menus.id", ondelete="CASCADE"), nullable=True, index=True
    )
    route_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    path: Mapped[str] = mapped_column(String(300))
    component: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(100))
    icon: Mapped[str] = mapped_column(String(100), default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    menu_type: Mapped[str] = mapped_column(String(20), default="page")
    permission_code: Mapped[str | None] = mapped_column(
        String(120), unique=True, nullable=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    roles: Mapped[list[Role]] = relationship(
        secondary=role_menu_table,
        back_populates="menus",
        lazy="selectin",
    )
