from __future__ import annotations

from datetime import datetime

from app.schemas.camel_model import CamelModel
from pydantic import Field


class TestModuleVO(CamelModel):
    """返回给前端的功能模块树节点。"""

    id: int
    project_id: int
    parent_id: int | None
    name: str
    code: str
    description: str
    order_no: int
    asset_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime
    children: list[TestModuleVO] = Field(default_factory=list)
