"""环境数据源、元数据快照和智能查询历史的数据访问层。"""

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models import DataQueryExecution, DataSourceMetadataSnapshot, EnvironmentDataSource, TestEnvironment
from app.repositories.base_repository import BaseRepository


class DataQueryRepository(BaseRepository):
    """只负责平台数据库持久化，不连接被测业务数据库。"""

    async def list_sources(self, project_id: int, environment_id: int | None) -> list[EnvironmentDataSource]:
        conditions = [EnvironmentDataSource.project_id == project_id]
        if environment_id is not None:
            conditions.append(EnvironmentDataSource.environment_id == environment_id)
        return list(
            (
                await self.session.scalars(
                    select(EnvironmentDataSource).where(*conditions).order_by(EnvironmentDataSource.id.desc())
                )
            ).all()
        )

    async def get_source(self, project_id: int, source_id: int) -> EnvironmentDataSource | None:
        return await self.session.scalar(
            select(EnvironmentDataSource).where(
                EnvironmentDataSource.project_id == project_id,
                EnvironmentDataSource.id == source_id,
            )
        )

    async def get_project_environment(self, project_id: int, environment_id: int) -> TestEnvironment | None:
        return await self.session.scalar(
            select(TestEnvironment).where(
                TestEnvironment.project_id == project_id,
                TestEnvironment.id == environment_id,
            )
        )

    async def get_metadata(self, source_id: int) -> DataSourceMetadataSnapshot | None:
        return await self.session.scalar(
            select(DataSourceMetadataSnapshot).where(DataSourceMetadataSnapshot.data_source_id == source_id)
        )

    async def get_metadata_for_update(self, source_id: int) -> DataSourceMetadataSnapshot | None:
        """锁定元数据快照，避免并发刷新产生重复记录。"""
        return await self.session.scalar(
            select(DataSourceMetadataSnapshot)
            .where(DataSourceMetadataSnapshot.data_source_id == source_id)
            .with_for_update()
        )

    async def list_history(
        self,
        project_id: int,
        environment_id: int | None,
        source_id: int | None,
        current: int,
        size: int,
    ) -> tuple[list[DataQueryExecution], int]:
        conditions = [DataQueryExecution.project_id == project_id]
        if environment_id is not None:
            conditions.append(DataQueryExecution.environment_id == environment_id)
        if source_id is not None:
            conditions.append(DataQueryExecution.data_source_id == source_id)
        total = int(await self.session.scalar(select(func.count(DataQueryExecution.id)).where(*conditions)) or 0)
        records = list(
            (
                await self.session.scalars(
                    select(DataQueryExecution)
                    .options(selectinload(DataQueryExecution.data_source))
                    .where(*conditions)
                    .order_by(DataQueryExecution.id.desc())
                    .offset((current - 1) * size)
                    .limit(size)
                )
            ).all()
        )
        return records, total

    async def get_execution(self, project_id: int, execution_id: int) -> DataQueryExecution | None:
        return await self.session.scalar(
            select(DataQueryExecution).options(selectinload(DataQueryExecution.data_source)).where(
                DataQueryExecution.project_id == project_id,
                DataQueryExecution.id == execution_id,
            )
        )
