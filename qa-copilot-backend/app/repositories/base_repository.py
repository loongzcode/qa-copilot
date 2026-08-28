from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """封装所有仓储共用的事务操作，Service 不直接操作数据库会话。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, entity: Any) -> None:
        self.session.add(entity)

    async def delete(self, entity: Any) -> None:
        await self.session.delete(entity)

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(self, entity: Any) -> None:
        await self.session.refresh(entity)
