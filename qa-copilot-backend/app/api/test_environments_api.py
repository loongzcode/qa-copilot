from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.service_deps.test_environments_api import TestEnvironmentsApiServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, success
from app.schemas.dto.test_environments import TestEnvironmentCreateDTO, TestEnvironmentUpdateDTO
from app.schemas.vo.test_environments import TestEnvironmentConnectionResultVO, TestEnvironmentVO

router = APIRouter(prefix="/test_environments", tags=["测试环境管理"])

@router.get(
    "/{project_id}/environments",
    response_model=ApiResult[list[TestEnvironmentVO]],
    dependencies=[
        Depends(
            require_permission(
                Permission.PROJECT_ENVIRONMENT_VIEW
            )
        )
    ],
    summary="查询测试环境列表",
)
async def list_environments(
        project_id: int,
        current_user: CurrentUser,
        service: TestEnvironmentsApiServiceDep,
        keyword: str = "",
        enabled: Annotated[bool | None, Query()] = None,
) ->  ApiResult[list[TestEnvironmentVO]]:
    environments = await service.list_environments(
        project_id,
        current_user,
        keyword,
        enabled,
    )
    return success(environments)

@router.post(
    "/{project_id}/environments",
    response_model=ApiResult[TestEnvironmentVO],
    dependencies=[
        Depends(
            require_permission(
                Permission.PROJECT_ENVIRONMENT_MANAGE
            )
        )
    ],
    summary="创建测试环境",
)
async def create_environment(
        project_id: int,
        current_user: CurrentUser,
        service: TestEnvironmentsApiServiceDep,
        payload: TestEnvironmentCreateDTO
)->ApiResult[TestEnvironmentVO]:
    environment = await service.create_environment(project_id,current_user,payload)
    return success(environment, "测试环境创建成功")

@router.put(
    "/{project_id}/environments/{environment_id}",
    response_model=ApiResult[TestEnvironmentVO],
    dependencies=[
        Depends(
            require_permission(
                Permission.PROJECT_ENVIRONMENT_MANAGE
            )
        )
    ],
    summary="编辑测试环境",
)
async def update_environment(project_id: int, environment_id: int,
        payload: TestEnvironmentUpdateDTO,current_user: CurrentUser,
        service: TestEnvironmentsApiServiceDep ) -> ApiResult[TestEnvironmentVO]:
    environment = await service.update_environment(project_id,environment_id,current_user,payload)
    return success(environment,"测试环境更新成功")

@router.delete("/{project_id}/environments/{environment_id}",
               response_model=ApiResult[None],
               dependencies=[
                   Depends(
                       require_permission(
                           Permission.PROJECT_ENVIRONMENT_MANAGE
                       )
                   )
               ])
async def delete_environment(project_id: int, environment_id: int,current_user: CurrentUser,
                             service: TestEnvironmentsApiServiceDep ) -> ApiResult[None]:
    await service.delete_environment(project_id,environment_id,current_user)
    return success(message="测试环境删除成功")

@router.post("/{project_id}/environments/{environment_id}/test",
             response_model=ApiResult[TestEnvironmentConnectionResultVO],
             dependencies=[
                 Depends(
                     require_permission(
                           Permission.PROJECT_ENVIRONMENT_TEST
                     )
                 )
             ])
async def test_environment(project_id: int, environment_id: int, current_user: CurrentUser,
                     service: TestEnvironmentsApiServiceDep ) -> ApiResult[TestEnvironmentConnectionResultVO]:
    result = await service.test_connection(
        project_id,
        environment_id,
        current_user,
    )
    return success(result)
