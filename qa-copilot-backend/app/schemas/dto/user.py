from pydantic import Field

from app.schemas.camel_model import CamelModel


class UserCreateDTO(CamelModel):
    """创建系统用户时接收的数据。"""

    username: str = Field(min_length=4, max_length=64)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=128)
    is_active: bool = True
    role_ids: list[int] = Field(default_factory=list)


class UserUpdateDTO(CamelModel):
    """编辑系统用户时接收的数据；只更新实际传入的字段。"""

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    is_active: bool | None = None
    role_ids: list[int] | None = None
