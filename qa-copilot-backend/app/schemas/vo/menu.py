from datetime import datetime

from app.core.constants import MenuType
from app.schemas.camel_model import CamelModel


class MenuVO(CamelModel):
    """菜单管理接口返回的目录、页面或按钮权限。"""

    id: int
    parent_id: int | None
    route_name: str
    path: str
    component: str
    title: str
    icon: str
    order: int
    menu_type: MenuType
    permission_code: str | None
    enabled: bool
    hidden: bool
    created_at: datetime
    updated_at: datetime
