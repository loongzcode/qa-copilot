from sqlalchemy import Text, cast, or_, select
from sqlalchemy.orm import selectinload

from app.models import TestEnvironment
from app.repositories.base_repository import BaseRepository


class TestEnvironmentsApiRepository(BaseRepository):
    async def list_environments(
            self,
            project_id: int,
            keyword: str,
            enabled: bool | None,
    ) -> list[TestEnvironment]:
        conditions = [TestEnvironment.project_id == project_id]
        if enabled is not None:
            conditions.append(TestEnvironment.enabled == enabled)
        if keyword:
            conditions.append(
                or_(
                    TestEnvironment.name.contains(keyword),
                    TestEnvironment.base_url.contains(keyword),
                    cast(
                        TestEnvironment.allowed_hosts,
                        Text,
                    ).contains(keyword),
                )
            )
        result = await self.session.scalars(
            select(TestEnvironment)
            .options(selectinload(TestEnvironment.creator))
            .where(*conditions)
            .order_by(TestEnvironment.id.desc())
        )
        return list(result.all())

    """
        根据环境 ID 查询环境
        并且确认这个环境属于指定项目
        同时加载创建人
    """
    async def get_environment(
            self,
            project_id: int,
            environment_id: int,
    ) -> TestEnvironment | None:
        return await self.session.scalar(
            select(TestEnvironment)
            .options(selectinload(TestEnvironment.creator))
            .where(TestEnvironment.id == environment_id, TestEnvironment.project_id == project_id)
        )