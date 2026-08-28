from fastapi import APIRouter, Depends

from app.api.service_deps.test_modules import TestModulesServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, success
from app.schemas.dto.test_modules import TestModuleCreateDTO, TestModuleUpdateDTO
from app.schemas.vo.test_modules import TestModuleVO

router = APIRouter(prefix="/test_modules", tags=["功能模块"])


@router.get(
    "/{project_id}/modules",
    response_model=ApiResult[list[TestModuleVO]],
    dependencies=[Depends(require_permission(Permission.PROJECT_MODULE_VIEW))],
    summary="查询项目功能模块",
)
async def list_modules(
    project_id: int,
    current_user: CurrentUser,
    service: TestModulesServiceDep,
    keyword: str = "",
) -> ApiResult[list[TestModuleVO]]:
    modules = await service.list_modules(
        project_id,
        current_user,
        keyword,
    )
    return success(modules)


@router.post(
    "/{project_id}/modules",
    response_model=ApiResult[TestModuleVO],
    dependencies=[Depends(require_permission(Permission.PROJECT_MODULE_MANAGE))],
    summary="创建项目功能模块",
)
async def create_module(
    project_id: int,
    payload: TestModuleCreateDTO,
    current_user: CurrentUser,
    service: TestModulesServiceDep,
) -> ApiResult[TestModuleVO]:
    module = await service.create_module(
        project_id,
        payload,
        current_user,
    )
    return success(module, "功能模块创建成功")


@router.put(
    "/{project_id}/modules/{module_id}",
    response_model=ApiResult[TestModuleVO],
    dependencies=[
        Depends(require_permission(Permission.PROJECT_MODULE_MANAGE))
    ],
    summary="编辑项目功能模块",
)
async def update_module(
    project_id: int,
    module_id: int,
    payload: TestModuleUpdateDTO,
    current_user: CurrentUser,
    service: TestModulesServiceDep,
) -> ApiResult[TestModuleVO]:
    module = await service.update_module(
        project_id,
        module_id,
        payload,
        current_user,
    )
    return success(module, "功能模块更新成功")


@router.delete(
    "/{project_id}/modules/{module_id}",
    response_model=ApiResult[None],
    dependencies=[
        Depends(require_permission(Permission.PROJECT_MODULE_MANAGE))
    ],
    summary="删除项目功能模块",
)
async def delete_module(
    project_id: int,
    module_id: int,
    current_user: CurrentUser,
    service: TestModulesServiceDep,
) -> ApiResult[None]:
    await service.delete_module(
        project_id,
        module_id,
        current_user,
    )
    return success(message="功能模块删除成功")