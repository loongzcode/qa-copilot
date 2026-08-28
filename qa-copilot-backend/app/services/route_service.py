from app.models import Menu, User
from app.repositories.route_repository import RouteRepository

"""
allowed_menus 管权限
_sorted_menus 管顺序
_route_dict 管格式
_build_route_tree 管层级
_home_route_name 管首页
user_route_config 负责把它们串起来
"""


class RouteService:
    def __init__(self, repository: RouteRepository) -> None:
        self.repository = repository

    async def user_routes(self, user: User) -> dict:
        menus = await self.allowed_menus(user)
        return {
            "routes": self._build_route_tree(menus),
            "home": self._home_route_name(menus),
        }

    """
    读取所有启用菜单
    → 排除 button 类型
    → 超管返回全部
    → 普通用户根据角色筛选
    → 补齐被授权页面的父目录
    """

    async def allowed_menus(self, user: User) -> list[Menu]:
        # Page and directory menus define Vue routes; button menus are only permissions.
        all_menus = [
            menu for menu in await self.repository.list_menus(enable_only=True) if menu.menu_type != "button"
        ]
        if user.is_superuser:
            return all_menus
        allowed_ids = {
            menu.id
            for role in user.roles
            if role.enabled
            for menu in role.menus
            if menu.enabled and menu.menu_type != "button"
        }
        # 只授权子页面时，也把它的父目录补齐，否则前端无法组成菜单树。
        by_id = {menu.id: menu for menu in all_menus}
        for menu_id in list(allowed_ids):
            parent_id = by_id.get(menu_id).parent_id if by_id.get(menu_id) else None
            while parent_id and parent_id in by_id:
                allowed_ids.add(parent_id)
                parent_id = by_id[parent_id].parent_id
        return [menu for menu in all_menus if menu.id in allowed_ids]

    # 重新组装父子结构
    @classmethod
    def _build_route_tree(cls, menus: list[Menu]) -> list[dict]:
        route_map = {menu.id: cls._route_dict(menu) for menu in menus}
        roots: list[dict] = []
        for menu in cls._sorted_menus(menus):
            route = route_map[menu.id]
            if menu.parent_id and menu.parent_id in route_map:
                route_map[menu.parent_id].setdefault("children", []).append(route)
            else:
                roots.append(route)
        return roots

    # 把数据库模型转成前端格式
    @staticmethod
    def _route_dict(menu: Menu) -> dict:
        meta: dict = {"title": menu.title, "order": menu.order, "hideInMenu": menu.hidden}
        if menu.icon:
            meta["icon"] = menu.icon
        return {
            "id": str(menu.id),
            "name": menu.route_name,
            "path": menu.path,
            "component": menu.component,
            "meta": meta,
        }

    # 把菜单树按显示顺序摊平
    @staticmethod
    def _sorted_menus(menus: list[Menu]) -> list[Menu]:
        """按菜单树的显示顺序展开，保证默认首页与左侧菜单第一项一致。"""
        # 菜单列表转换成字典
        menu_ids = {menu.id: menu for menu in menus}
        children = {}
        for menu in menus:
            # 父菜单在当前用户的菜单列表中：正常挂到父菜单下面。
            # 父菜单不在当前用户的菜单列表中：把当前菜单作为根菜单。
            parent_id = menu.parent_id if menu.parent_id in menu_ids else None
            children.setdefault(parent_id, []).append(menu)
        for record in children.values():
            record.sort(key=lambda item: (item.order, item.id))
        result = []
        visited = set()

        # 递归展开菜单
        # 找到指定父节点的所有子菜单
        # 跳过已经处理过的菜单
        # 把当前菜单加入结果
        # 递归处理当前菜单的子菜单
        def append_branch(parent_id: int | None) -> None:
            for menu in children.get(parent_id, []):
                if menu.id in visited:
                    continue
                visited.add(menu.id)
                result.append(menu)
                append_branch(menu.id)

        append_branch(None)
        # 数据异常形成循环时也不丢失菜单，同时避免无限递归。
        result.extend(menu for menu in menus if menu.id not in visited)
        return result

    # 选择默认首页
    @classmethod
    def _home_route_name(cls, menus: list[Menu]) -> str:
        """选择用户菜单树中的第一个可见页面作为首页。"""

        ordered = cls._sorted_menus(menus)
        visible_page = next(
            (menu for menu in ordered if menu.menu_type == "page" and not menu.hidden),
            None,
        )
        if visible_page is not None:
            return visible_page.route_name

        # 极端情况下只有隐藏页面，仍优先进入一个有权限的业务页面。
        any_page = next((menu for menu in ordered if menu.menu_type == "page"), None)
        return any_page.route_name if any_page is not None else "403"

    async def route_exists(self, current_user: User, route_name: str) -> bool:
        return any(menu.route_name == route_name for menu in await self.allowed_menus(current_user))

