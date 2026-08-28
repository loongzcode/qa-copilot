"""自动化后台执行任务接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.service_deps.automation_execution_tasks import AutomationExecutionServiceDep
from app.core.constants import AutomationExecutionStatus
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.automation_execution_tasks import AutomationExecutionCreateDTO
from app.schemas.vo.automation_execution_tasks import AutomationExecutionReportVO, AutomationExecutionTaskVO

router = APIRouter(prefix="/automation-executions", tags=["自动化执行任务"])


@router.get(
    "/{project_id}",
    response_model=ApiResult[PageResult[AutomationExecutionTaskVO]],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_VIEW))],
)
async def list_automation_execution_tasks(
    project_id: int,
    current_user: CurrentUser,
    service: AutomationExecutionServiceDep,
    status: Annotated[AutomationExecutionStatus | None, Query()] = None,
    current: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
) -> ApiResult[PageResult[AutomationExecutionTaskVO]]:
    """分页查询任务状态；前端运行期间可定时刷新。"""
    records, total = await service.list_tasks(project_id, current_user, status, current, size)
    return success(PageResult(current=current, size=size, total=total, records=records))


@router.get(
    "/{project_id}/{task_id}",
    response_model=ApiResult[AutomationExecutionReportVO],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_VIEW))],
)
async def get_automation_execution_report(
    project_id: int,
    task_id: int,
    current_user: CurrentUser,
    service: AutomationExecutionServiceDep,
) -> ApiResult[AutomationExecutionReportVO]:
    """读取任务级汇总和逐步骤脱敏报告。"""
    return success(await service.get_report(project_id, task_id, current_user))


@router.post(
    "/{project_id}",
    response_model=ApiResult[AutomationExecutionTaskVO],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_RUN))],
)
async def submit_automation_execution_task(
    project_id: int,
    payload: AutomationExecutionCreateDTO,
    current_user: CurrentUser,
    service: AutomationExecutionServiceDep,
) -> ApiResult[AutomationExecutionTaskVO]:
    """提交一条后台任务；只有已审批定义和非生产启用环境会入队。"""
    return success(await service.submit_task(project_id, payload, current_user), "执行任务已提交")


@router.post(
    "/{project_id}/{task_id}/cancel",
    response_model=ApiResult[AutomationExecutionTaskVO],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_RUN))],
)
async def cancel_automation_execution_task(
    project_id: int,
    task_id: int,
    current_user: CurrentUser,
    service: AutomationExecutionServiceDep,
) -> ApiResult[AutomationExecutionTaskVO]:
    """取消等待任务，或请求 Worker 终止正在运行的 Pytest 子进程。"""
    return success(await service.cancel_task(project_id, task_id, current_user), "取消请求已处理")
