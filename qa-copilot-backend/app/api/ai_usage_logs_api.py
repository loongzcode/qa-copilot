"""AI 调用日志的列表、详情与统计接口。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.service_deps.ai_usage_logs import AIUsageLogsServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.ai_usage_logs import AIUsageLogsFilterDTO, AIUsageLogsQueryDTO
from app.schemas.vo.ai_usage_logs import AIUsageLogDetailVO, AIUsageLogListVO, AIUsageLogStatisticsVO

router = APIRouter(prefix="/ai_usage_logs", tags=["调用日志"])


@router.get(
    "/list",
    response_model=ApiResult[PageResult[AIUsageLogListVO]],
    dependencies=[
        Depends(
            require_permission(
                Permission.AI_USAGE_VIEW
            )
        )
    ],
    summary="查询日志列表"
)
async def list_logs(
        _: CurrentUser,
        service: AIUsageLogsServiceDep,
        query: Annotated[AIUsageLogsQueryDTO, Query()]
)-> ApiResult[PageResult[AIUsageLogListVO]]:
    records, total = await service.list_logs(query)
    return success(PageResult(current=query.current,size=query.size,total=total,records=records))

@router.get(
    "/statistics",
    response_model=ApiResult[AIUsageLogStatisticsVO],
    dependencies=[
        Depends(
            require_permission(
                Permission.AI_USAGE_VIEW
            )
        )
    ],
)
async def get_statistics(
        _:CurrentUser,
        service:AIUsageLogsServiceDep,
        query: Annotated[AIUsageLogsFilterDTO, Query()]
) -> ApiResult[AIUsageLogStatisticsVO]:
    result = await service.get_statistics(query)
    return success(result,"查询成功")

@router.get(
    "/detail/{log_id}",
    response_model=ApiResult[AIUsageLogDetailVO],
    dependencies=[
        Depends(
            require_permission(
                Permission.AI_USAGE_VIEW
            )
        )
    ]
)
async def get_log_detail(
        _:CurrentUser,
        service:AIUsageLogsServiceDep,
        log_id: Annotated[int, Path(gt=0)]
) ->ApiResult[AIUsageLogDetailVO]:
    result = await service.get_log_detail(log_id)
    return success(result,"查询成功")
