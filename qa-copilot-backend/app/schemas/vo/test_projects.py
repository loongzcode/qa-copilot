from datetime import datetime

from app.core.constants import ProjectStatus
from app.schemas.camel_model import CamelModel
from pydantic import Field


class TestProjectVO(CamelModel):
    """返回给前端的项目信息。"""

    id: int
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(min_length=1, max_length=64)
    description: str
    owner_id: int | None
    owner_name: str | None
    member_count: int = Field(default=0, ge=0)
    module_count: int = Field(default=0, ge=0)
    status: ProjectStatus
    updated_at: datetime

