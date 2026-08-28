"""AI 需求拆解任务接口。

开发从 API 契约开始：本文件接下来会同时定义“提交拆解任务”和“查询任务状态”
两个入口。路由在方法完成前不注册到 main.py，避免半成品影响现有系统。
"""

from fastapi import APIRouter, Depends

from app.api.service_deps.requirement_extraction import RequirementExtractionServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, success
from app.schemas.dto.requirements import RequirementExtractionSubmitDTO
from app.schemas.vo.requirements import RequirementExtractionTaskVO

router = APIRouter(prefix="/requirements", tags=["AI 需求拆解"])

@router.post(
     "/{project_id}/{requirement_id}/extract",
    response_model=ApiResult[RequirementExtractionTaskVO],
    dependencies=[
        Depends(
            require_permission(
                Permission.REQUIREMENT_EXTRACT
            )
        )
    ],
    summary="提交拆解任务"
)
async def submit_extraction(
        project_id:int,
        requirement_id:int,
        current_user:CurrentUser,
        service:RequirementExtractionServiceDep,
        payload:RequirementExtractionSubmitDTO
)->ApiResult[RequirementExtractionTaskVO]:
    result = await service.submit_extraction(project_id,requirement_id,payload,current_user)
    return success(result,"提交成功")

@router.get(
     "/{project_id}/{requirement_id}/extraction-tasks/latest",
    response_model=ApiResult[RequirementExtractionTaskVO | None],
    dependencies=[
        Depends(
            require_permission(
                Permission.REQUIREMENT_VIEW
            )
        )
    ],
    summary="查询最新任务，用于用户刷新或重新进入页面后恢复进度"
)
async def get_latest_task(
        project_id:int,
        requirement_id:int,
        current_user:CurrentUser,
        service:RequirementExtractionServiceDep
)->ApiResult[RequirementExtractionTaskVO | None]:
    result = await service.get_latest_task(project_id,requirement_id,current_user)
    return success(result,"查询成功")

@router.get(
     "/{project_id}/{requirement_id}/extraction-tasks/{task_id}",
    response_model=ApiResult[RequirementExtractionTaskVO],
    dependencies=[
        Depends(
            require_permission(
                Permission.REQUIREMENT_VIEW
            )
        )
    ],
    summary="根据任务 ID 轮询准确的任务"
)
async def get_task(
        project_id:int,
        requirement_id:int,
        task_id:int,
        current_user:CurrentUser,
        service:RequirementExtractionServiceDep
)->ApiResult[RequirementExtractionTaskVO]:
    result = await service.get_task(project_id,requirement_id,task_id,current_user)
    return success(result,"查询成功")
