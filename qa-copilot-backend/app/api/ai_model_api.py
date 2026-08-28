from fastapi import APIRouter, Depends

from app.api.service_deps.ai_model import AIModelServiceDep
from app.core.deps import CurrentUser, RequestId, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, success
from app.schemas.dto.ai_model import AIConnectionTestDTO, AIModelCreateDTO, AIModelUpdateDTO
from app.schemas.vo.ai_model import AIConnectionResultVO, AIModelVO

router = APIRouter(prefix="/ai-model", tags=["ai模型管理"])


@router.get(
    "/list", response_model=ApiResult[list[AIModelVO]], dependencies=[Depends(require_permission(Permission.AI_VIEW))]
)
async def list_models(_: CurrentUser, service: AIModelServiceDep) -> ApiResult[list[AIModelVO]]:
    return success(await service.list_model())


@router.post(
    "/models",
    response_model=ApiResult[AIModelVO],
    dependencies=[Depends(require_permission(Permission.AI_MODEL_CREATE))],
)
async def create_model(payload: AIModelCreateDTO, _: CurrentUser, service: AIModelServiceDep) -> ApiResult[AIModelVO]:
    return success(await service.create_model(payload), "AI 模型创建成功")


@router.put(
    "/models/{model_pk}",
    response_model=ApiResult[AIModelVO],
    dependencies=[Depends(require_permission(Permission.AI_MODEL_UPDATE))],
)
async def update_model(
        model_pk: int, payload: AIModelUpdateDTO, _: CurrentUser, service: AIModelServiceDep
) -> ApiResult[AIModelVO]:
    return success(await service.update_model(model_pk, payload), "AI 模型更新成功")


@router.delete(
    "/models/{model_pk}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(Permission.AI_MODEL_DELETE))],
)
async def delete_model(model_pk: int, _: CurrentUser, service: AIModelServiceDep) -> ApiResult[None]:
    await service.delete_model(model_pk)
    return success(message="AI 模型删除成功")


@router.post(
    "/test",
    response_model=ApiResult[AIConnectionResultVO],
    dependencies=[Depends(require_permission(Permission.AI_MODEL_TEST))],
)
async def test_connection(
        payload: AIConnectionTestDTO, current_user: CurrentUser, request_id: RequestId, service: AIModelServiceDep
) -> ApiResult[AIConnectionResultVO]:
    return success(await service.test_connection(
        payload,
        current_user,
        request_id,
    ), "连接测试成功")
