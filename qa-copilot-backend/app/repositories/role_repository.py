from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Menu, Role
from app.repositories.base_repository import BaseRepository


class RoleRepository(BaseRepository):
    async def get_options(self):
        statement = select(Role).where(Role.enabled.is_(True)).order_by(Role.id.desc())
        result = await self.session.scalars(statement)
        return list(result.all())

    async def list_roles(self):
        return list(
            (await self.session.scalars(select(Role).options(selectinload(Role.menus)).order_by(Role.id.desc()))).all()
        )

    async def get_menus(self, menu_ids):
        if not menu_ids:
            return []
        result = await self.session.scalars(select(Menu).where(Menu.id.in_(menu_ids)))

        return list(result.all())

    async def get_role(self, role_id, with_menus: bool = False):
        statement = select(Role).where(Role.id == role_id)
        if with_menus:
            statement = statement.options(selectinload(Role.menus))
        return await self.session.scalar(statement)