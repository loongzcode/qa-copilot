from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.params import Depends

from app.api.service_deps.test_projects import TestProjectsServiceDep
from app.core.constants import ProjectStatus
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.test_projects import TestProjectCreateDTO, TestProjectUpdateDTO
from app.schemas.vo.test_projects import TestProjectVO

router = APIRouter(prefix="/projects", tags=["项目信息"])


@router.get(
    "/list",
    response_model=ApiResult[PageResult[TestProjectVO]],
    dependencies=[Depends(require_permission(Permission.PROJECT_INFO_VIEW))],
)
async def list_projects(
    current_user: CurrentUser,
    service: TestProjectsServiceDep,
    current: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    keyword: str = "",
    status: Annotated[
        ProjectStatus | None,
        Query(),
    ] = None,
) -> ApiResult[PageResult[TestProjectVO]]:
    records, total = await service.list_projects(
        current_user, current, size, keyword, status
    )
    return success(PageResult(current=current, size=size, total=total, records=records))


@router.post(
    "/create",
    response_model=ApiResult[TestProjectVO],
    dependencies=[Depends(require_permission(Permission.PROJECT_INFO_CREATE))],
)
async def create_project(
    payload: TestProjectCreateDTO,
    current_user: CurrentUser,
    service: TestProjectsServiceDep,
):
    return success(await service.create_project(payload, current_user), "项目创建成功")


@router.put(
    "/update/{project_id}",
    response_model=ApiResult[TestProjectVO],
    dependencies=[Depends(require_permission(Permission.PROJECT_INFO_UPDATE))],
)
async def update_project(
    project_id: int,
    payload: TestProjectUpdateDTO,
    current_user: CurrentUser,
    service: TestProjectsServiceDep,
):
    return success(await service.update_project(project_id, payload, current_user))


@router.put(
    "/archive/{project_id}",
    response_model=ApiResult[TestProjectVO],
    dependencies=[Depends(require_permission(Permission.PROJECT_INFO_ARCHIVE))],
)
async def archive_project(
    project_id: int,
    current_user: CurrentUser,
    service: TestProjectsServiceDep,
):
    project = await service.archive_project(
        project_id,
        current_user,
    )
    return success(project, "项目归档成功")


@router.put(
    "/start/{project_id}",
    response_model=ApiResult[TestProjectVO],
    dependencies=[Depends(require_permission(Permission.PROJECT_INFO_UPDATE))],
)
async def start_project(
    project_id: int, current_user: CurrentUser, service: TestProjectsServiceDep
):
    project = await service.start_project(
        project_id,
        current_user,
    )
    return success(project, "项目启动成功")
