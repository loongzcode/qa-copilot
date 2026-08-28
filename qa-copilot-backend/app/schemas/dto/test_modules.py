from typing import Any

from pydantic import Field, field_validator

from app.schemas.camel_model import CamelModel


class TestModuleBaseDTO(CamelModel):
    """新增和编辑功能模块共用的基础字段。"""

    name: str = Field(min_length=1, max_length=160)
    code: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    )
    description: str = Field(default="", max_length=2000)
    order_no: int = Field(default=0, ge=0)

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value


class TestModuleCreateDTO(TestModuleBaseDTO):
    """新建一级模块或子模块。parent_id 为空时表示一级模块。"""

    parent_id: int | None = Field(default=None, gt=0)


class TestModuleUpdateDTO(CamelModel):
    """编辑模块；只更新请求中实际传入的字段。"""

    parent_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    code: str | None = Field(
        default=None,
        min_length=2,
        max_length=80,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    )
    description: str | None = Field(default=None, max_length=2000)
    order_no: int | None = Field(default=None, ge=0)

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value
