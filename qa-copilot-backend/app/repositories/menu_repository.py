from sqlalchemy import func, select

from app.models import Menu
from app.repositories.base_repository import BaseRepository


class MenuRepository(BaseRepository):
    async def get_menu(self, menu_id: int) -> Menu | None:
        return await self.session.get(Menu, menu_id)

    async def list_menus(self, enabled_only: bool = False) -> list[Menu]:
        statement = select(Menu)
        if enabled_only:
            statement = statement.where(Menu.enabled.is_(True))
        return list((await self.session.scalars(statement.order_by(Menu.order, Menu.id))).all())

    async def count_menu_children(self, menu_id):
        return await self.session.scalar(select(func.count(Menu.id)).where(Menu.parent_id == menu_id)) or 0
