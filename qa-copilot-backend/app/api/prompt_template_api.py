from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.service_deps.prompt_templates import PromptTemplateServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.prompt_templates import (
    PromptTemplateCreateDTO,
    PromptTemplatePreviewDTO,
    PromptTemplateUpdateDTO,
    PromptTextPreviewDTO,
)
from app.schemas.vo.prompt_templates import PromptTemplateListVO, PromptTemplatePreviewVO, PromptTemplateVO

router = APIRouter(prefix="/prompt_templates", tags=["提示词模板管理"])


@router.post(
    "/preview/render",
    response_model=ApiResult[PromptTemplatePreviewVO],
    dependencies=[Depends(require_permission(Permission.AI_PROMPT_VIEW))],
    summary="预览尚未保存的最终 Prompt",
)
async def preview_prompt_text(
    payload: PromptTextPreviewDTO,
    service: PromptTemplateServiceDep,
    _: CurrentUser,
) -> ApiResult[PromptTemplatePreviewVO]:
    return success(service.preview_text(payload))


@router.get(
    "",
    response_model=ApiResult[PageResult[PromptTemplateListVO]],
    dependencies=[Depends(require_permission(Permission.AI_PROMPT_VIEW))],
    summary="查询提示词模板列表",
)
async def get_prompt_template_list(
    service: PromptTemplateServiceDep,
    _: CurrentUser,
    keyword: str = "",
    enabled: Annotated[bool | None, Query()] = None,
    current: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
) -> ApiResult[PageResult[PromptTemplateListVO]]:
    records, total = await service.list_templates(
        keyword=keyword,
        enabled=enabled,
        current=current,
        size=size,
    )

    return success(
        PageResult(
            current=current,
            size=size,
            total=total,
            records=records,
        )
    )


@router.get(
    "/{prompt_id}",
    response_model=ApiResult[PromptTemplateVO],
    dependencies=[Depends(require_permission(Permission.AI_PROMPT_VIEW))],
    summary="查询提示词模板详情",
)
async def get_prompt_template(
    prompt_id: Annotated[int, Path(gt=0)],
    service: PromptTemplateServiceDep,
    _: CurrentUser,
) -> ApiResult[PromptTemplateVO]:
    prompt = await service.get_template(prompt_id=prompt_id)
    return success(prompt)


@router.post(
    "",
    response_model=ApiResult[PromptTemplateVO],
    dependencies=[Depends(require_permission(Permission.AI_PROMPT_MANAGE))],
    summary="新增提示词模板",
)
async def create_prompt_template(
    payload: PromptTemplateCreateDTO,
    service: PromptTemplateServiceDep,
    _: CurrentUser,
) -> ApiResult[PromptTemplateVO]:
    prompt = await service.create_template(payload=payload)
    return success(prompt, "创建 Prompt 模板成功")


@router.put(
    "/{prompt_id}",
    response_model=ApiResult[PromptTemplateVO],
    dependencies=[Depends(require_permission(Permission.AI_PROMPT_MANAGE))],
    summary="更新提示词模板",
)
async def update_prompt_template(
    prompt_id: Annotated[int, Path(gt=0)],
    payload: PromptTemplateUpdateDTO,
    service: PromptTemplateServiceDep,
    _: CurrentUser,
) -> ApiResult[PromptTemplateVO]:
    prompt = await service.update_template(
        prompt_id=prompt_id,
        payload=payload,
    )
    return success(prompt, "更新 Prompt 模板成功")


@router.post(
    "/{prompt_id}/preview",
    response_model=ApiResult[PromptTemplatePreviewVO],
    dependencies=[Depends(require_permission(Permission.AI_PROMPT_VIEW))],
    summary="预览变量替换后的最终 Prompt",
)
async def preview_prompt_template(
    prompt_id: Annotated[int, Path(gt=0)],
    payload: PromptTemplatePreviewDTO,
    service: PromptTemplateServiceDep,
    _: CurrentUser,
) -> ApiResult[PromptTemplatePreviewVO]:
    return success(await service.preview_template(prompt_id, payload))


@router.delete(
    "/{prompt_id}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(Permission.AI_PROMPT_MANAGE))],
    summary="删除提示词模板",
)
async def delete_prompt_template(
    prompt_id: Annotated[int, Path(gt=0)],
    service: PromptTemplateServiceDep,
    _: CurrentUser,
) -> ApiResult[None]:
    await service.delete_template(prompt_id=prompt_id)
    return success(message="删除 Prompt 模板成功")
