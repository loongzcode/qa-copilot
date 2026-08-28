from fastapi import APIRouter, Depends, Query

from app.api.service_deps.user import UserServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.user import UserCreateDTO, UserUpdateDTO
from app.schemas.vo.user import UserVO

router = APIRouter(prefix="/user", tags=["用户管理"])


@router.get(
    "/list",
    response_model=ApiResult[PageResult[UserVO]],
    dependencies=[Depends(require_permission(Permission.SYSTEM_USER_VIEW))],
)
async def get_users(
    _: CurrentUser,
    service: UserServiceDep,
    current: int = Query(1, ge=1),
    size: int = Query(1, ge=1),
    keyword: str = "",
) -> ApiResult[PageResult[UserVO]]:
    records, total = await service.list_users(current, size, keyword)
    return success(PageResult(current=current, size=size, total=total, records=records))


@router.post(
    "/create",
    response_model=ApiResult[UserVO],
    dependencies=[Depends(require_permission(Permission.SYSTEM_USER_CREATE))],
)
async def create_user(payload: UserCreateDTO, _: CurrentUser, service: UserServiceDep) -> ApiResult[UserVO]:
    return success(await service.create_user(payload), "用户创建成功")


@router.put(
    "/update/{user_id}",
    response_model=ApiResult[UserVO],
    dependencies=[Depends(require_permission(Permission.SYSTEM_USER_UPDATE))],
)
async def update_user(
    user_id: int,
    payload: UserUpdateDTO,
    current_user: CurrentUser,
    service: UserServiceDep,
) -> ApiResult[UserVO]:
    return success(await service.update_user(user_id, payload, current_user.id), "用户更新成功")

@router.delete(
    "/delete/{user_id}",
    response_model=ApiResult[UserVO],
    dependencies=[Depends(require_permission(Permission.SYSTEM_USER_DELETE))],
)
async def delete_user(user_id: int,current_user: CurrentUser, service: UserServiceDep) -> ApiResult[UserVO]:
    return success(await service.delete_user(user_id,current_user),"用户删除成功")
