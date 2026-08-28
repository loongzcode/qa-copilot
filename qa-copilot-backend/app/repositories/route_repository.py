from sqlalchemy import select

from app.models import Menu
from app.repositories.base_repository import BaseRepository


class RouteRepository(BaseRepository):
    async def list_menus(self, enable_only: bool = False) -> list[Menu]:
        statement = select(Menu)
        if enable_only:
            statement = statement.where(Menu.enabled.is_(True))
        return list((await self.session.scalars(statement.order_by(Menu.order,Menu.id))).all())
