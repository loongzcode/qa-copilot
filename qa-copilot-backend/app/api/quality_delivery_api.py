"""需求、用例和自动化多 Agent 协作状态接口。"""

from fastapi import APIRouter, Depends

from app.api.service_deps.quality_delivery import QualityDeliveryServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, success
from app.schemas.vo.quality_delivery import QualityDeliveryStatusVO

router = APIRouter(prefix="/quality-delivery", tags=["质量交付协作"])


@router.get(
    "/{project_id}/requirements/{requirement_id}/status",
    response_model=ApiResult[QualityDeliveryStatusVO],
    dependencies=[Depends(require_permission(Permission.REQUIREMENT_VIEW))],
)
async def get_quality_delivery_status(
    project_id: int,
    requirement_id: int,
    current_user: CurrentUser,
    service: QualityDeliveryServiceDep,
) -> ApiResult[QualityDeliveryStatusVO]:
    """查询协调状态；接口只读，不会替用户审批需求点或发布测试用例。"""
    return success(await service.get_status(project_id, requirement_id, current_user))
