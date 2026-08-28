from typing import Any

from pydantic import Field, field_validator

from app.schemas.camel_model import CamelModel


class TestProjectCreateDTO(CamelModel):
    """创建测试项目时接收的请求参数。"""

    name: str = Field(min_length=1, max_length=160)
    code: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Z][A-Z0-9_-]*$",
    )
    description: str = Field(default="", max_length=2000)

    # 前端不传时由 Service 使用当前登录用户 ID。
    # 即使普通用户传了其他 ID，Service 也不能直接信任；只有管理员可以指定负责人。
    owner_id: int | None = Field(default=None, gt=0)


    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        """去除名称和说明两侧无意义的空格。"""
        return value.strip() if isinstance(value, str) else value

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: Any) -> Any:
        """项目编码统一去除两侧空格并转换成大写。"""

        return value.strip().upper() if isinstance(value, str) else value


class TestProjectUpdateDTO(CamelModel):
    """编辑项目时接收的请求参数。"""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
    )
    owner_id: int | None = Field(
        default=None,
        gt=0,
    )

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value