from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, literal, text
from sqlalchemy.orm import Mapped, mapped_column, query_expression, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.test_projects import TestProjects


class TestModule(TimestampMixin, Base):
    """项目功能模块，使用 parent_id 组成树形结构。"""

    __tablename__ = "test_modules"

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "code",
            name="uq_test_modules_project_code",
        ),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id",
            name="chk_test_modules_not_self_parent",
        ),
        Index("ix_test_modules_project_parent", "project_id", "parent_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_modules.id", ondelete="CASCADE"),
        nullable=True,
        default=None,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
    )
    order_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    project: Mapped[TestProjects] = relationship(
        "TestProjects",
        foreign_keys=[project_id],
        lazy="selectin",
    )
    parent: Mapped[TestModule | None] = relationship(
        "TestModule",
        back_populates="children",
        foreign_keys=[parent_id],
        remote_side=[id],
    )
    children: Mapped[list[TestModule]] = relationship(
        "TestModule",
        back_populates="parent",
        foreign_keys=[parent_id],
        cascade="all, delete-orphan",
        single_parent=True,
    )

    # 当前资产表尚未接入模块查询，先提供默认值，后续由查询动态填充。
    asset_count: Mapped[int] = query_expression(literal(0))
