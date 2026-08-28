from fastapi import APIRouter, Depends

from app.api.service_deps.role import RoleServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, success
from app.schemas.dto.role import RoleCreateDTO, RoleUpdateDTO
from app.schemas.vo.role import RoleOptionVO, RoleVO

router = APIRouter(prefix="/role",tags=["权限管理"])

@router.get("/options",response_model=ApiResult[list[RoleOptionVO]])
async def get_options(service: RoleServiceDep) -> ApiResult[list[RoleOptionVO]]:
    roles = await service.get_options()
    return ApiResult(data=roles)


@router.get("/list",response_model=ApiResult[list[RoleVO]]
            ,dependencies=[Depends(require_permission(Permission.SYSTEM_ROLE_VIEW))])
async def get_role_list(_:CurrentUser,service: RoleServiceDep) -> ApiResult[list[RoleVO]]:
    return success(await service.list_roles())


@router.post("/create",response_model=ApiResult[RoleVO],
             dependencies=[Depends(require_permission(Permission.SYSTEM_ROLE_CREATE))])
async def create_role(payload:RoleCreateDTO,_:CurrentUser,service: RoleServiceDep,) -> ApiResult[RoleVO]:
    return success(await service.create_role(payload), "角色创建成功")

@router.put("/update/{role_id}",response_model=ApiResult[RoleVO],
            dependencies=[Depends(require_permission(Permission.SYSTEM_ROLE_UPDATE))])
async def update_role(
        role_id: int,
        payload: RoleUpdateDTO,
        _: CurrentUser,
        service: RoleServiceDep) -> ApiResult[RoleVO]:
    return success(await service.update_role(role_id, payload), "角色更新成功")


@router.delete("/delete/{role_id}",response_model=ApiResult[None],
               dependencies=[Depends(require_permission(Permission.SYSTEM_ROLE_DELETE))])
async def delete_role(role_id: int, _: CurrentUser, service: RoleServiceDep):
    await service.delete_role(role_id)
    return success(message="角色删除成功")
