from sqlalchemy.exc import IntegrityError

from app.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models import Menu
from app.repositories.menu_repository import MenuRepository
from app.schemas.vo.menu import MenuVO


class MenuService:
    def __init__(self, repository: MenuRepository) -> None:
        self.repository: MenuRepository = repository

    async def list_menus(self) -> list[MenuVO]:
        return [MenuVO.model_validate(menu) for menu in await self.repository.list_menus()]

    async def create_menu(self, payload):
        menu = Menu(**payload.model_dump())
        await self._validate_menu(menu)
        self.repository.add(menu)
        try:
            await self.repository.commit()
        except IntegrityError as e:
            await self.repository.rollback()
            raise ConflictException("路由名称或权限编码已经存在") from e
        return MenuVO.model_validate(menu)

    async def update_menu(self, menu_id, payload):
        menu = await self.repository.get_menu(menu_id)
        if menu is None:
            raise NotFoundException("菜单不存在")
        changes = payload.model_dump(exclude_unset=True)
        if changes.get("parent_id") == menu.id:
            raise BadRequestException("菜单不能成为自己的父级")
        for key, value in changes.items():
            setattr(menu, key, value)
        await self._validate_menu(menu)
        try:
            await self.repository.commit()
        except IntegrityError as e:
            await self.repository.rollback()
            raise ConflictException("路由名称或权限编码已经存在") from e
        return MenuVO.model_validate(menu)

    async def delete_menu(self, menu_id):
        menu = await self.repository.get_menu(menu_id)
        if menu is None:
            raise NotFoundException("菜单不存在")
        if await self.repository.count_menu_children(menu_id):
            raise BadRequestException("请先删除子菜单或按钮权限")
        await self.repository.delete(menu)
        await self.repository.commit()


    async def _validate_menu(self, menu: Menu) -> None:
        parent = None
        if menu.parent_id is not None:
            parent = await self.repository.get_menu(menu.parent_id)
            if parent is None:
                raise BadRequestException("父菜单不存在")
            if parent.menu_type == "button":
                raise BadRequestException("按钮权限下面不能继续添加菜单")
        if menu.menu_type == "button":
            if parent is None or parent.menu_type != "page":
                raise BadRequestException("按钮权限必须挂在页面菜单下面")
            if not menu.permission_code:
                raise BadRequestException("按钮权限必须填写权限编码")
            menu.path = ""
            menu.component = ""
            menu.hidden = True
            menu.permission_code = menu.permission_code.strip().lower()
        else:
            if not menu.path or not menu.component:
                raise BadRequestException("目录和页面必须填写路由路径与组件标识")
            menu.permission_code = None
