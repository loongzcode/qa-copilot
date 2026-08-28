"""通知渠道管理和连通性测试接口。"""

from fastapi import APIRouter, Depends, Path

from app.api.service_deps.notification_channels import NotificationChannelServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, success
from app.schemas.dto.notification_channels import NotificationChannelCreateDTO, NotificationChannelUpdateDTO
from app.schemas.vo.notification_channels import NotificationChannelTestResultVO, NotificationChannelVO

router = APIRouter(prefix="/notification-channels", tags=["通知渠道"])


@router.get(
    "",
    response_model=ApiResult[list[NotificationChannelVO]],
    dependencies=[Depends(require_permission(Permission.NOTIFICATION_VIEW))],
)
async def list_notification_channels(
    _: CurrentUser,
    service: NotificationChannelServiceDep,
) -> ApiResult[list[NotificationChannelVO]]:
    """返回脱敏后的通知渠道列表。"""
    return success(await service.list_channels())


@router.post(
    "",
    response_model=ApiResult[NotificationChannelVO],
    dependencies=[Depends(require_permission(Permission.NOTIFICATION_CREATE))],
)
async def create_notification_channel(
    payload: NotificationChannelCreateDTO,
    _: CurrentUser,
    service: NotificationChannelServiceDep,
) -> ApiResult[NotificationChannelVO]:
    """创建并加密保存通知渠道。"""
    return success(await service.create_channel(payload), "通知渠道创建成功")


@router.put(
    "/{channel_id}",
    response_model=ApiResult[NotificationChannelVO],
    dependencies=[Depends(require_permission(Permission.NOTIFICATION_UPDATE))],
)
async def update_notification_channel(
    payload: NotificationChannelUpdateDTO,
    _: CurrentUser,
    service: NotificationChannelServiceDep,
    channel_id: int = Path(gt=0),
) -> ApiResult[NotificationChannelVO]:
    """更新通知渠道，未提交新密钥时保留原密文。"""
    return success(await service.update_channel(channel_id, payload), "通知渠道更新成功")


@router.delete(
    "/{channel_id}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(Permission.NOTIFICATION_DELETE))],
)
async def delete_notification_channel(
    _: CurrentUser,
    service: NotificationChannelServiceDep,
    channel_id: int = Path(gt=0),
) -> ApiResult[None]:
    """删除通知渠道。"""
    await service.delete_channel(channel_id)
    return success(message="通知渠道删除成功")


@router.post(
    "/{channel_id}/test",
    response_model=ApiResult[NotificationChannelTestResultVO],
    dependencies=[Depends(require_permission(Permission.NOTIFICATION_TEST))],
)
async def test_notification_channel(
    _: CurrentUser,
    service: NotificationChannelServiceDep,
    channel_id: int = Path(gt=0),
) -> ApiResult[NotificationChannelTestResultVO]:
    """使用保存的密钥发送一条真实测试消息。"""
    return success(await service.test_channel(channel_id))

