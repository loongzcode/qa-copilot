from pydantic import Field

from app.schemas.camel_model import CamelModel


class LoginDTO(CamelModel):
    """账号密码登录参数。"""

    username: str = Field(alias="userName", min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RefreshTokenDTO(CamelModel):
    """刷新访问令牌时接收的参数。"""

    refresh_token: str
