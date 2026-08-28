from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.selectable import and_

from app.models import TestProjectMember, User
from app.repositories.base_repository import BaseRepository


class TestProjectMembersRepository(BaseRepository):
    async def list_members(self, project_id, current, size, keyword):
        conditions = [TestProjectMember.project_id == project_id]
        keyword = keyword.strip()
        if keyword:
            conditions.append(or_(User.username.contains(keyword), User.display_name.contains(keyword)))
        total_query = (
            select(func.count())
            .select_from(TestProjectMember)
            .join(User, TestProjectMember.user_id == User.id)
            .where(*conditions)
        )
        total = await self.session.scalar(total_query) or 0

        list_query = (
            select(TestProjectMember)
            .join(User, TestProjectMember.user_id == User.id)
            .options(selectinload(TestProjectMember.user))
            .where(*conditions)
            .order_by(TestProjectMember.created_at.desc())
            .offset((current - 1) * size)
            .limit(size)
        )
        members = list((await self.session.scalars(list_query)).all())
        return members, total

    async def get_member(self, project_id, user_id) -> TestProjectMember | None:
        return await self.session.scalar(
            select(TestProjectMember)
            .options(selectinload(TestProjectMember.user))
            .where(TestProjectMember.project_id == project_id, TestProjectMember.user_id == user_id)
        )

    async def list_member_options(self, project_id, keyword, limit) -> list[User]:
        conditions = [User.is_active.is_(True), TestProjectMember.user_id.is_(None)]
        keyword = keyword.strip()
        if keyword:
            conditions.append(or_(User.username.contains(keyword), User.display_name.contains(keyword)))
        query = (
            select(User)
            .outerjoin(
                TestProjectMember,
                and_(
                    TestProjectMember.user_id == User.id,
                    TestProjectMember.project_id == project_id,
                ),
            )
            .where(*conditions)
            .order_by(User.display_name.asc(), User.id.asc())
            .limit(limit)
        )
        return list((await self.session.scalars(query)).all())
