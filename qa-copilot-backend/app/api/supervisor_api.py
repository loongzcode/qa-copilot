"""Supervisor 规划运行的创建、查询和取消接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.service_deps.supervisor import SupervisorServiceDep
from app.core.constants import SupervisorRunStatus
from app.core.deps import CurrentUser, RequestId, get_permission_codes, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.supervisor import SupervisorApprovalDTO, SupervisorCreateRunDTO
from app.schemas.vo.supervisor import SupervisorRunDetailVO, SupervisorRunVO

router = APIRouter(prefix="/supervisor", tags=["Supervisor Agent"])


@router.post(
    "/projects/{project_id}/runs",
    response_model=ApiResult[SupervisorRunDetailVO],
    dependencies=[Depends(require_permission(Permission.SUPERVISOR_RUN))],
)
async def create_supervisor_run(
    payload: SupervisorCreateRunDTO,
    current_user: CurrentUser,
    request_id: RequestId,
    service: SupervisorServiceDep,
    project_id: Annotated[int, Path(gt=0)],
) -> ApiResult[SupervisorRunDetailVO]:
    """为开放目标生成并保存受控计划；接口不会执行计划步骤。"""
    permissions = {code for code in get_permission_codes(current_user) if code}
    result = await service.create_plan(
        project_id,
        payload,
        current_user,
        permissions,
        request_id=request_id,
    )
    return success(result, "Supervisor 计划生成完成")


@router.get(
    "/projects/{project_id}/runs",
    response_model=ApiResult[PageResult[SupervisorRunVO]],
    dependencies=[Depends(require_permission(Permission.SUPERVISOR_VIEW))],
)
async def list_supervisor_runs(
    current_user: CurrentUser,
    service: SupervisorServiceDep,
    project_id: Annotated[int, Path(gt=0)],
    status: Annotated[SupervisorRunStatus | None, Query()] = None,
    current: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
) -> ApiResult[PageResult[SupervisorRunVO]]:
    """分页查看项目内运行；列表不返回每一步的大块参数和结果。"""
    records, total = await service.list_runs(project_id, current_user, current, size, status)
    return success(PageResult(current=current, size=size, total=total, records=records))


@router.get(
    "/projects/{project_id}/runs/{run_id}",
    response_model=ApiResult[SupervisorRunDetailVO],
    dependencies=[Depends(require_permission(Permission.SUPERVISOR_VIEW))],
)
async def get_supervisor_run_detail(
    current_user: CurrentUser,
    service: SupervisorServiceDep,
    project_id: Annotated[int, Path(gt=0)],
    run_id: Annotated[int, Path(gt=0)],
) -> ApiResult[SupervisorRunDetailVO]:
    """查看一次运行的上下文快照、安全决定和全部计划步骤。"""
    return success(await service.get_run_detail(project_id, run_id, current_user))


@router.post(
    "/projects/{project_id}/runs/{run_id}/cancel",
    response_model=ApiResult[SupervisorRunDetailVO],
    dependencies=[Depends(require_permission(Permission.SUPERVISOR_RUN))],
)
async def cancel_supervisor_run(
    current_user: CurrentUser,
    service: SupervisorServiceDep,
    project_id: Annotated[int, Path(gt=0)],
    run_id: Annotated[int, Path(gt=0)],
) -> ApiResult[SupervisorRunDetailVO]:
    """取消尚未执行的运行；还会同步取消其中仍处于待处理状态的步骤。"""
    return success(await service.cancel_run(project_id, run_id, current_user), "Supervisor 运行已取消")


@router.post(
    "/projects/{project_id}/runs/{run_id}/execute",
    response_model=ApiResult[SupervisorRunDetailVO],
    dependencies=[Depends(require_permission(Permission.SUPERVISOR_RUN))],
)
async def execute_supervisor_run(
    current_user: CurrentUser,
    service: SupervisorServiceDep,
    project_id: Annotated[int, Path(gt=0)],
    run_id: Annotated[int, Path(gt=0)],
) -> ApiResult[SupervisorRunDetailVO]:
    """把已就绪计划可靠地提交到后台顺序执行，接口本身不等待执行完成。"""
    return success(
        await service.request_execution(project_id, run_id, current_user),
        "Supervisor 执行任务已提交",
    )


@router.post(
    "/projects/{project_id}/runs/{run_id}/steps/{step_id}/approval",
    response_model=ApiResult[SupervisorRunDetailVO],
    dependencies=[Depends(require_permission(Permission.SUPERVISOR_APPROVE))],
)
async def decide_supervisor_step_approval(
    payload: SupervisorApprovalDTO,
    current_user: CurrentUser,
    service: SupervisorServiceDep,
    project_id: Annotated[int, Path(gt=0)],
    run_id: Annotated[int, Path(gt=0)],
    step_id: Annotated[int, Path(gt=0)],
) -> ApiResult[SupervisorRunDetailVO]:
    """批准或驳回风险步骤；最后一项获批后自动提交后台执行。"""
    return success(
        await service.decide_step_approval(
            project_id,
            run_id,
            step_id,
            payload,
            current_user,
        ),
        "Supervisor 审批决定已保存",
    )
