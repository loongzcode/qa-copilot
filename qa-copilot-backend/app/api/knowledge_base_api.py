from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.service_deps.knowledge_base import KnowledgeBaseServiceDep
from app.api.service_deps.knowledge_search import KnowledgeSearchServiceDep
from app.core.constants import AIModelTaskType
from app.core.deps import CurrentUser, RequestId, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.knowledge_bases import (
    KnowledgeBaseCreateDTO,
    KnowledgeBaseUpdateDTO,
    KnowledgeSearchDTO,
)
from app.schemas.vo.knowledge_bases import (
    KnowledgeBaseVO,
    KnowledgeModelOptionVO,
    KnowledgeSearchResultVO,
)

router = APIRouter(prefix="/knowledge_bases", tags=["知识库管理"])


@router.get(
    "/model-options",
    response_model=ApiResult[list[KnowledgeModelOptionVO]],
    dependencies=[
        Depends(
            require_permission(
                Permission.KNOWLEDGE_BASE_MANAGE
            )
        )
    ],
    summary="查询知识库可选模型",
)
async def list_knowledge_model_options(
    task_type: Annotated[AIModelTaskType, Query(alias="taskType")],
    _: CurrentUser,
    service: KnowledgeBaseServiceDep,
) -> ApiResult[list[KnowledgeModelOptionVO]]:
    return success(await service.list_model_options(task_type))

@router.get("/{project_id}/bases", response_model=ApiResult[PageResult[KnowledgeBaseVO]],
            dependencies=[Depends(require_permission(Permission.KNOWLEDGE_BASE_VIEW))])
async def list_knowledge_bases(
        project_id: int,
        current_user: CurrentUser,
        service: KnowledgeBaseServiceDep,
        keyword: str = "",
        enabled: Annotated[bool | None, Query()] = None,
        current: int = Query(default=1, ge=1),
        size: int = Query(default=10, ge=1, le=100)
) -> ApiResult[PageResult[KnowledgeBaseVO]]:
    records, total = await service.list_knowledge_bases(project_id,current_user,keyword,enabled,current,size)
    return success(
        PageResult(
            current=current,
            size=size,
            total=total,
            records=records,
        )
    )

@router.post(
    "/{project_id}/bases",
    response_model=ApiResult[KnowledgeBaseVO],
    dependencies=[
        Depends(
            require_permission(
                Permission.KNOWLEDGE_BASE_MANAGE
            )
        )
    ],
    summary="创建知识库",
)
async def create_knowledge_base(
        project_id: int,
        payload:KnowledgeBaseCreateDTO,
        current_user: CurrentUser,
        service: KnowledgeBaseServiceDep)-> ApiResult[KnowledgeBaseVO]:
    knowledge_base = await service.create_knowledge_base(project_id,current_user,payload)
    return success(knowledge_base,"创建知识库成功")


@router.put("/{project_id}/bases/{knowledge_base_id}",
            response_model=ApiResult[KnowledgeBaseVO],
            dependencies=[Depends(
                require_permission(Permission.KNOWLEDGE_BASE_MANAGE)
            )],
            summary="更新知识库")
async def update_knowledge_base(
        project_id: int,
        knowledge_base_id: int,
        payload: KnowledgeBaseUpdateDTO,
        current_user: CurrentUser,
        service: KnowledgeBaseServiceDep
)-> ApiResult[KnowledgeBaseVO]:
    knowledge_base = await service.update_knowledge_base(project_id,knowledge_base_id,current_user,payload)
    return success(knowledge_base,"知识库更新成功")


@router.delete(
    "/{project_id}/bases/{knowledge_base_id}",
    response_model=ApiResult[None],
    dependencies=[
        Depends(
            require_permission(
                Permission.KNOWLEDGE_BASE_MANAGE
            )
        )
    ],
    summary="删除知识库",
)
async def delete_knowledge_base(
    project_id: int,
    knowledge_base_id: int,
    current_user: CurrentUser,
    service: KnowledgeBaseServiceDep,
) -> ApiResult[None]:
    await service.delete_knowledge_base(
        project_id,
        knowledge_base_id,
        current_user,
    )
    return success(message="知识库删除成功")


@router.post(
    "/{project_id}/bases/{knowledge_base_id}/search",
    response_model=ApiResult[list[KnowledgeSearchResultVO]],
    dependencies=[Depends(require_permission(Permission.KNOWLEDGE_BASE_VIEW))],
    summary="知识库检索"
)
async def search_knowledge_base(
        project_id: int,
        knowledge_base_id: int,
        current_user: CurrentUser,
        request_id: RequestId,
        service: KnowledgeSearchServiceDep,
        payload:KnowledgeSearchDTO
)->ApiResult[list[KnowledgeSearchResultVO]]:
    search_results = await service.search_knowledge_base(
        project_id,
        knowledge_base_id,
        current_user,
        payload,
        request_id,
    )
    return success(search_results,"检索成功")
