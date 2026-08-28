"""原子需求点新增、校正、删除和批量确认接口。"""

from fastapi import APIRouter, Depends

from app.api.service_deps.requirement_items import RequirementItemsServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, success
from app.schemas.dto.requirements import (
    RequirementItemCreateDTO,
    RequirementItemsConfirmDTO,
    RequirementItemUpdateDTO,
)
from app.schemas.vo.requirements import RequirementDetailVO, RequirementItemVO

router = APIRouter(prefix="/requirements", tags=["原子需求点管理"])


@router.post(
    "/{project_id}/{requirement_id}/items",
    response_model=ApiResult[RequirementItemVO],
    dependencies=[Depends(require_permission(Permission.REQUIREMENT_MANAGE))],
)
async def create_requirement_item(
    project_id: int,
    requirement_id: int,
    payload: RequirementItemCreateDTO,
    current_user: CurrentUser,
    service: RequirementItemsServiceDep,
) -> ApiResult[RequirementItemVO]:
    item = await service.create_requirement_item(
        project_id,
        requirement_id,
        payload,
        current_user,
    )
    return success(item, "需求点添加成功")


@router.put(
    "/{project_id}/{requirement_id}/items/{item_id}",
    response_model=ApiResult[RequirementItemVO],
    dependencies=[Depends(require_permission(Permission.REQUIREMENT_MANAGE))],
)
async def update_requirement_item(
    project_id: int,
    requirement_id: int,
    item_id: int,
    payload: RequirementItemUpdateDTO,
    current_user: CurrentUser,
    service: RequirementItemsServiceDep,
) -> ApiResult[RequirementItemVO]:
    item = await service.update_requirement_item(
        project_id,
        requirement_id,
        item_id,
        payload,
        current_user,
    )
    return success(item, "需求点更新成功")


@router.delete(
    "/{project_id}/{requirement_id}/items/{item_id}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(Permission.REQUIREMENT_MANAGE))],
)
async def delete_requirement_item(
    project_id: int,
    requirement_id: int,
    item_id: int,
    current_user: CurrentUser,
    service: RequirementItemsServiceDep,
) -> ApiResult[None]:
    await service.delete_requirement_item(
        project_id,
        requirement_id,
        item_id,
        current_user,
    )
    return success(message="需求点删除成功")


@router.post(
    "/{project_id}/{requirement_id}/items/confirm",
    response_model=ApiResult[RequirementDetailVO],
    dependencies=[Depends(require_permission(Permission.REQUIREMENT_MANAGE))],
)
async def confirm_requirement_items(
    project_id: int,
    requirement_id: int,
    payload: RequirementItemsConfirmDTO,
    current_user: CurrentUser,
    service: RequirementItemsServiceDep,
) -> ApiResult[RequirementDetailVO]:
    requirement = await service.confirm_requirement_items(
        project_id,
        requirement_id,
        payload,
        current_user,
    )
    return success(requirement, "需求点确认成功")
