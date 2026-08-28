from datetime import datetime

from app.schemas.camel_model import CamelModel


class RoleVO(CamelModel):
    """角色管理列表和新增、编辑接口返回的数据。"""

    id: int
    code: str
    name: str
    description: str
    enabled: bool
    menu_ids: list[int]
    is_system: bool
    created_at: datetime
    updated_at: datetime


class RoleOptionVO(CamelModel):
    """用户选择角色时使用的精简选项。"""

    id: int
    name: str
    code: str
