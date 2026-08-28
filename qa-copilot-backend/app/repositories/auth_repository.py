from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Role, User
from app.repositories.base_repository import BaseRepository


class AuthRepository(BaseRepository):

    async def get_by_username(self, username: str) -> User | None:
        return await self.session.scalar(
            statement=select(User).where(User.username == username)
        )

    async def get_by_id(
        self, user_id: int, with_permissions: bool = False
    ) -> User | None:
        user = select(User).where(User.id == user_id)
        if with_permissions:
            user = user.options(selectinload(User.roles).selectinload(Role.menus))
        return await self.session.scalar(user)
