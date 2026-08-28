from fastapi import APIRouter, Depends

from app.api.service_deps.ai_providers import AiProviderServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, success
from app.schemas.dto.ai_provider import AIProviderCreateDTO, AIProviderUpdateDTO
from app.schemas.vo.ai_provider import AIProviderVO

router = APIRouter(prefix="/ai_provider", tags=["ai服务商管理"])


@router.get(
    "/list",
    response_model=ApiResult[list[AIProviderVO]],
    dependencies=[Depends(require_permission(Permission.AI_VIEW))],
)
async def get_provider_list(_: CurrentUser, service: AiProviderServiceDep) -> ApiResult[list[AIProviderVO]]:
    return success(await service.list_providers())


@router.post(
    "/create",
    response_model=ApiResult[AIProviderVO],
    dependencies=[Depends(require_permission(Permission.AI_PROVIDER_CREATE))],
)
async def create_provider(
    payload: AIProviderCreateDTO, _: CurrentUser, service: AiProviderServiceDep
) -> ApiResult[AIProviderVO]:
    return success(await service.create_provider(payload), "AI 服务商创建成功")


@router.put(
    "/update/{provider_id}",
    response_model=ApiResult[AIProviderVO],
    dependencies=[Depends(require_permission(Permission.AI_PROVIDER_UPDATE))],
)
async def update_provider(
    provider_id: int, payload: AIProviderUpdateDTO, _: CurrentUser, service: AiProviderServiceDep
) -> ApiResult[AIProviderVO]:
    return success(await service.update_provider(provider_id, payload), "AI 服务商更新成功")


@router.delete(
    "/providers/{provider_id}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(Permission.AI_PROVIDER_DELETE))],
)
async def delete_provider(provider_id: int, _: CurrentUser, service: AiProviderServiceDep) -> ApiResult[None]:
    await service.delete_provider(provider_id)
    return success(message="AI 服务商删除成功")
