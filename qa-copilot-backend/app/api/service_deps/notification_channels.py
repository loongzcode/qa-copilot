"""通知渠道 API 的请求级依赖组装。"""

from typing import Annotated

from app.core.deps import DbSession
from app.repositories.notification_channel_repository import NotificationChannelRepository
from app.services.notification_channel_service import NotificationChannelService
from fastapi import Depends


def get_notification_channel_service(db: DbSession) -> NotificationChannelService:
    """让 Repository 和 Service 共用当前请求的数据库 Session。"""
    return NotificationChannelService(NotificationChannelRepository(db))


NotificationChannelServiceDep = Annotated[
    NotificationChannelService,
    Depends(get_notification_channel_service),
]
