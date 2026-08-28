from pydantic import Field, model_validator

from app.core.constants import MenuType
from app.schemas.camel_model import CamelModel


class MenuBaseDTO(CamelModel):
    """创建目录、页面和按钮权限时使用的公共字段。"""

    parent_id: int | None = Field(default=None, gt=0)
    route_name: str = Field(min_length=1, max_length=120)
    path: str = Field(default="", max_length=300)
    component: str = Field(default="", max_length=200)
    title: str = Field(min_length=1, max_length=100)
    icon: str = Field(default="", max_length=100)
    order: int = Field(default=0, ge=0, le=9999)
    menu_type: MenuType = MenuType.PAGE
    permission_code: str | None = Field(default=None, max_length=120)
    enabled: bool = True
    hidden: bool = False

    @model_validator(mode="after")
    def validate_menu_fields(self) -> MenuBaseDTO:
        if self.menu_type == MenuType.BUTTON:
            if self.parent_id is None:
                raise ValueError("按钮权限必须选择所属页面")
            if not self.permission_code:
                raise ValueError("按钮权限必须填写权限编码")
        elif not self.path or not self.component:
            raise ValueError("目录和页面必须填写路由路径与组件标识")
        return self


class MenuCreateDTO(MenuBaseDTO):
    """创建菜单或按钮权限参数。"""


class MenuUpdateDTO(CamelModel):
    """编辑菜单或按钮权限参数。"""

    parent_id: int | None = Field(default=None, gt=0)
    path: str | None = Field(default=None, max_length=300)
    component: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=100)
    icon: str | None = Field(default=None, max_length=100)
    order: int | None = Field(default=None, ge=0, le=9999)
    menu_type: MenuType | None = None
    permission_code: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None
    hidden: bool | None = None
