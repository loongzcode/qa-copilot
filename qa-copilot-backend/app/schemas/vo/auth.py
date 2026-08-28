from app.schemas.camel_model import CamelModel


class LoginVO(CamelModel):
    """登录或刷新令牌成功后的令牌信息。"""

    token: str
    refresh_token: str
