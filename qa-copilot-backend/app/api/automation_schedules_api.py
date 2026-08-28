"""定时回归计划 API。"""

from fastapi import APIRouter, Depends, Path

from app.api.service_deps.automation_schedules import AutomationSchedulesServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, success
from app.schemas.dto.automation_schedules import AutomationScheduleCreateDTO, AutomationScheduleUpdateDTO
from app.schemas.vo.automation_schedules import AutomationScheduleVO

router = APIRouter(prefix="/automation-schedules", tags=["自动化定时回归"])


@router.get(
    "/{project_id}",
    response_model=ApiResult[list[AutomationScheduleVO]],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_VIEW))],
)
async def list_schedules(
    current_user: CurrentUser,
    service: AutomationSchedulesServiceDep,
    project_id: int = Path(gt=0),
) -> ApiResult[list[AutomationScheduleVO]]:
    return success(await service.list_schedules(project_id, current_user))


@router.post(
    "/{project_id}",
    response_model=ApiResult[AutomationScheduleVO],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_DEFINITION_MANAGE))],
)
async def create_schedule(
    payload: AutomationScheduleCreateDTO,
    current_user: CurrentUser,
    service: AutomationSchedulesServiceDep,
    project_id: int = Path(gt=0),
) -> ApiResult[AutomationScheduleVO]:
    return success(await service.create(project_id, payload, current_user), "定时回归计划已创建")


@router.put(
    "/{project_id}/{schedule_id}",
    response_model=ApiResult[AutomationScheduleVO],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_DEFINITION_MANAGE))],
)
async def update_schedule(
    payload: AutomationScheduleUpdateDTO,
    current_user: CurrentUser,
    service: AutomationSchedulesServiceDep,
    project_id: int = Path(gt=0),
    schedule_id: int = Path(gt=0),
) -> ApiResult[AutomationScheduleVO]:
    return success(await service.update(project_id, schedule_id, payload, current_user), "定时回归计划已更新")


@router.delete(
    "/{project_id}/{schedule_id}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_DEFINITION_MANAGE))],
)
async def delete_schedule(
    current_user: CurrentUser,
    service: AutomationSchedulesServiceDep,
    project_id: int = Path(gt=0),
    schedule_id: int = Path(gt=0),
) -> ApiResult[None]:
    await service.delete(project_id, schedule_id, current_user)
    return success(message="定时回归计划已删除")
