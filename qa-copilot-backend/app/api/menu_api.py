from fastapi import APIRouter, Depends

from app.api.service_deps.menu import MenuServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, success
from app.schemas.dto.menu import MenuCreateDTO, MenuUpdateDTO
from app.schemas.vo.menu import MenuVO

router = APIRouter(prefix="/menu", tags=["菜单管理"])


@router.get(
    "/list",
    response_model=ApiResult[list[MenuVO]],
    dependencies=[Depends(require_permission(Permission.SYSTEM_MENU_VIEW))],
)
async def list_menus(_: CurrentUser, service: MenuServiceDep) -> ApiResult[list[MenuVO]]:
    return success(await service.list_menus())


@router.post(
    "/create",
    response_model=ApiResult[MenuVO],
    dependencies=[Depends(require_permission(Permission.SYSTEM_MENU_CREATE))],
)
async def create_menu(payload: MenuCreateDTO, _: CurrentUser, service: MenuServiceDep) -> ApiResult[MenuVO]:
    return success(await service.create_menu(payload), "菜单创建成功")


@router.put(
    "/update/{menu_id}",
    response_model=ApiResult[MenuVO],
    dependencies=[Depends(require_permission(Permission.SYSTEM_MENU_UPDATE))],
)
async def update_menu(
    menu_id: int, payload: MenuUpdateDTO, _: CurrentUser, service: MenuServiceDep
) -> ApiResult[MenuVO]:
    return success(await service.update_menu(menu_id, payload), "菜单更新成功")


@router.delete(
    "/delete/{menu_id}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(Permission.SYSTEM_MENU_DELETE))],
)
async def delete_menu(menu_id: int, _: CurrentUser, service: MenuServiceDep) -> ApiResult[None]:
    await service.delete_menu(menu_id)
    return success(message="菜单删除成功")
