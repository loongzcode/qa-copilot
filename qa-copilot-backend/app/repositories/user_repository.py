from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.models import Role, User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository):
    async def list_users(self, current, size, keyword) -> tuple[list[User], int]:
        conditions = []
        if keyword:
            conditions.append(or_(User.username.contains(keyword), User.display_name.contains(keyword)))
        total = await self.session.scalar(select(func.count(User.id)).where(*conditions)) or 0
        records = list(
            (
                await self.session.scalars(
                    select(User)
                    .where(*conditions)
                    .options(selectinload(User.roles))
                    .order_by(User.id.desc())
                    .offset((current - 1) * size)
                    .limit(size)
                )
            ).all()
        )
        return records, total

    async def get_roles(self, role_ids):
        # 判断为空，为空返回空列表
        if not role_ids:
            return []
        # 返回查询到达role列表
        return list((await self.session.scalars(select(Role).where(Role.id.in_(set(role_ids))))).all())

    async def get_user(self, user_id: int, with_roles: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id)
        if with_roles:
            statement = statement.options(selectinload(User.roles))
        return await self.session.scalar(statement)