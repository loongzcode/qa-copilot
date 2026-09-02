"""测试环境智能数据查询 HTTP 接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.service_deps.data_query import DataQueryServiceDep
from app.core.deps import CurrentUser, RequestId, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.data_query import (
    DataQueryExecuteDTO,
    DataQueryHistoryQueryDTO,
    EnvironmentDataSourceCreateDTO,
    EnvironmentDataSourceUpdateDTO,
)
from app.schemas.vo.data_query import (
    DataQueryExecutionVO,
    DataSourceConnectionResultVO,
    DataSourceMetadataVO,
    EnvironmentDataSourceVO,
)

router = APIRouter(prefix="/data-query", tags=["智能数据查询"])


@router.get(
    "/{project_id}/sources",
    response_model=ApiResult[list[EnvironmentDataSourceVO]],
    dependencies=[Depends(require_permission(Permission.DATA_QUERY_VIEW))],
    summary="查询环境数据源",
)
async def list_sources(
    project_id: Annotated[int, Path(gt=0)],
    current_user: CurrentUser,
    service: DataQueryServiceDep,
    environment_id: Annotated[int | None, Query(gt=0)] = None,
) -> ApiResult[list[EnvironmentDataSourceVO]]:
    return success(await service.list_sources(project_id, environment_id, current_user))


@router.post(
    "/{project_id}/sources",
    response_model=ApiResult[EnvironmentDataSourceVO],
    dependencies=[Depends(require_permission(Permission.DATA_QUERY_SOURCE_MANAGE))],
    summary="创建环境数据源",
)
async def create_source(
    project_id: Annotated[int, Path(gt=0)],
    payload: EnvironmentDataSourceCreateDTO,
    current_user: CurrentUser,
    service: DataQueryServiceDep,
) -> ApiResult[EnvironmentDataSourceVO]:
    return success(await service.create_source(project_id, payload, current_user), "数据源创建成功")


@router.put(
    "/{project_id}/sources/{source_id}",
    response_model=ApiResult[EnvironmentDataSourceVO],
    dependencies=[Depends(require_permission(Permission.DATA_QUERY_SOURCE_MANAGE))],
    summary="编辑环境数据源",
)
async def update_source(
    project_id: Annotated[int, Path(gt=0)],
    source_id: Annotated[int, Path(gt=0)],
    payload: EnvironmentDataSourceUpdateDTO,
    current_user: CurrentUser,
    service: DataQueryServiceDep,
) -> ApiResult[EnvironmentDataSourceVO]:
    return success(await service.update_source(project_id, source_id, payload, current_user), "数据源更新成功")


@router.delete(
    "/{project_id}/sources/{source_id}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(Permission.DATA_QUERY_SOURCE_MANAGE))],
    summary="删除未产生审计记录的数据源",
)
async def delete_source(
    project_id: Annotated[int, Path(gt=0)],
    source_id: Annotated[int, Path(gt=0)],
    current_user: CurrentUser,
    service: DataQueryServiceDep,
) -> ApiResult[None]:
    await service.delete_source(project_id, source_id, current_user)
    return success(message="数据源删除成功")


@router.post(
    "/{project_id}/sources/{source_id}/test",
    response_model=ApiResult[DataSourceConnectionResultVO],
    dependencies=[Depends(require_permission(Permission.DATA_QUERY_SOURCE_MANAGE))],
    summary="测试数据源连接",
)
async def test_source(
    project_id: Annotated[int, Path(gt=0)],
    source_id: Annotated[int, Path(gt=0)],
    current_user: CurrentUser,
    service: DataQueryServiceDep,
) -> ApiResult[DataSourceConnectionResultVO]:
    return success(await service.test_source(project_id, source_id, current_user))


@router.post(
    "/{project_id}/sources/{source_id}/metadata",
    response_model=ApiResult[DataSourceMetadataVO],
    dependencies=[Depends(require_permission(Permission.DATA_QUERY_SOURCE_MANAGE))],
    summary="刷新数据源结构快照",
)
async def refresh_metadata(
    project_id: Annotated[int, Path(gt=0)],
    source_id: Annotated[int, Path(gt=0)],
    current_user: CurrentUser,
    service: DataQueryServiceDep,
) -> ApiResult[DataSourceMetadataVO]:
    return success(await service.refresh_metadata(project_id, source_id, current_user), "元数据刷新成功")


@router.get(
    "/{project_id}/sources/{source_id}/metadata",
    response_model=ApiResult[DataSourceMetadataVO],
    dependencies=[Depends(require_permission(Permission.DATA_QUERY_VIEW))],
    summary="查看数据源结构快照",
)
async def get_metadata(
    project_id: Annotated[int, Path(gt=0)],
    source_id: Annotated[int, Path(gt=0)],
    current_user: CurrentUser,
    service: DataQueryServiceDep,
) -> ApiResult[DataSourceMetadataVO]:
    return success(await service.get_metadata(project_id, source_id, current_user))


@router.post(
    "/{project_id}/execute",
    response_model=ApiResult[DataQueryExecutionVO],
    dependencies=[Depends(require_permission(Permission.DATA_QUERY_EXECUTE))],
    summary="执行自然语言数据查询",
)
async def execute_query(
    project_id: Annotated[int, Path(gt=0)],
    payload: DataQueryExecuteDTO,
    current_user: CurrentUser,
    request_id: RequestId,
    service: DataQueryServiceDep,
) -> ApiResult[DataQueryExecutionVO]:
    return success(await service.execute_query(project_id, payload, current_user, request_id), "查询完成")


@router.get(
    "/{project_id}/history",
    response_model=ApiResult[PageResult[DataQueryExecutionVO]],
    dependencies=[Depends(require_permission(Permission.DATA_QUERY_VIEW))],
    summary="查询智能数据查询历史",
)
async def list_history(
    project_id: Annotated[int, Path(gt=0)],
    current_user: CurrentUser,
    service: DataQueryServiceDep,
    query: Annotated[DataQueryHistoryQueryDTO, Query()],
) -> ApiResult[PageResult[DataQueryExecutionVO]]:
    return success(
        await service.list_history(
            project_id,
            current_user,
            query.environment_id,
            query.data_source_id,
            query.current,
            query.size,
        )
    )


@router.get(
    "/{project_id}/executions/{execution_id}",
    response_model=ApiResult[DataQueryExecutionVO],
    dependencies=[Depends(require_permission(Permission.DATA_QUERY_VIEW))],
    summary="查看智能数据查询详情",
)
async def get_execution(
    project_id: Annotated[int, Path(gt=0)],
    execution_id: Annotated[int, Path(gt=0)],
    current_user: CurrentUser,
    service: DataQueryServiceDep,
) -> ApiResult[DataQueryExecutionVO]:
    return success(await service.get_execution(project_id, execution_id, current_user))
