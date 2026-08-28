from typing import Any

from pydantic import Field, field_validator

from app.schemas.camel_model import CamelModel


class RoleBaseDTO(CamelModel):
    """创建角色时使用的公共字段。"""

    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    enabled: bool = True
    menu_ids: list[int] = Field(default_factory=list)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value


class RoleCreateDTO(RoleBaseDTO):
    """创建角色参数。"""


class RoleUpdateDTO(CamelModel):
    """编辑角色参数；角色编码创建后不可修改。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    menu_ids: list[int] | None = None
