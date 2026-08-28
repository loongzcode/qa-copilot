"""通知渠道的数据访问层。"""

from sqlalchemy import select

from app.models import NotificationChannel
from app.repositories.base_repository import BaseRepository


class NotificationChannelRepository(BaseRepository):
    """集中封装通知渠道查询，业务校验和密钥处理留在 Service。"""

    async def list_channels(self) -> list[NotificationChannel]:
        """按创建顺序返回全部渠道，供系统管理员维护。"""
        return list(
            (
                await self.session.scalars(
                    select(NotificationChannel).order_by(NotificationChannel.id)
                )
            ).all()
        )

    async def list_enabled_channels(self) -> list[NotificationChannel]:
        """返回所有启用渠道，供后台通知 Worker 筛选发送目标。"""
        return list(
            (
                await self.session.scalars(
                    select(NotificationChannel)
                    .where(NotificationChannel.enabled.is_(True))
                    .order_by(NotificationChannel.id)
                )
            ).all()
        )

    async def get_channel(self, channel_id: int) -> NotificationChannel | None:
        """按主键读取一个渠道。"""
        return await self.session.scalar(
            select(NotificationChannel).where(NotificationChannel.id == channel_id)
        )

