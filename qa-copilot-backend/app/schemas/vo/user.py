from datetime import datetime

from app.schemas.camel_model import CamelModel


class UserVO(CamelModel):
    """用户管理列表和新增、编辑接口返回的用户信息。"""

    id: int
    username: str
    display_name: str
    is_active: bool
    is_superuser: bool
    role_ids: list[int]
    role_codes: list[str]
    created_at: datetime
    updated_at: datetime


class UserInfoVO(CamelModel):
    """当前登录用户的前端权限信息。"""

    user_id: str
    user_name: str
    roles: list[str]
    buttons: list[str]
