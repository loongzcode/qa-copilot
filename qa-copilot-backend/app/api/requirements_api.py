"""需求管理接口。

开发顺序从 API 开始。下一步先完成“分页查询需求”这一个完整闭环：
API 定义输入输出 -> Service 组织权限与 VO -> Repository 生成查询。
路由尚未注册到 main.py，因此未完成代码不会影响现有系统。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.api.service_deps.knowledge_document import KnowledgeDocumentServiceDep
from app.api.service_deps.requirements import RequirementsServiceDep
from app.core.constants import KnowledgeDocumentType, RequirementStatus
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.knowledge_documents import KnowledgeDocumentUploadDTO
from app.schemas.dto.requirements import (
    RequirementCreateDTO,
    RequirementUpdateDTO,
)
from app.schemas.vo.knowledge_documents import KnowledgeDocumentVO
from app.schemas.vo.requirements import (
    RequirementDetailVO,
    RequirementFormOptionsVO,
    RequirementVO,
)

router = APIRouter(prefix="/requirements", tags=["需求管理"])


@router.get(
    "/{project_id}",
    response_model=ApiResult[PageResult[RequirementVO]],
    dependencies=[
        Depends(
            require_permission(
                Permission.REQUIREMENT_VIEW
            )
        )
    ]
)
async def list_requirements(
        project_id: int,
        current_user: CurrentUser,
        service: RequirementsServiceDep,
        keyword: Annotated[str, Query(max_length=300)] = "",
        status: Annotated[RequirementStatus | None, Query()] = None,
        current: Annotated[int, Query(ge=1)] = 1,
        size: Annotated[int, Query(ge=1, le=100)] = 10,
) -> ApiResult[PageResult[RequirementVO]]:
    records, total = await service.list_requirements(
        project_id,
        current_user,
        keyword,
        status,
        current,
        size
    )
    return success(PageResult(current=current, size=size, total=total, records=records))

@router.get(
    "/{project_id}/options",
    response_model=ApiResult[RequirementFormOptionsVO],
    dependencies=[
        Depends(
            require_permission(Permission.REQUIREMENT_VIEW)
        )
    ]
)
async def get_requirement_options(
        project_id: int,
        current_user:CurrentUser,
        service:RequirementsServiceDep
)->ApiResult[RequirementFormOptionsVO]:
    result = await service.get_form_options(project_id, current_user)
    return success(result,"查询成功")


@router.post(
    "/{project_id}/source-documents",
    response_model=ApiResult[KnowledgeDocumentVO],
    dependencies=[
        Depends(require_permission(Permission.REQUIREMENT_MANAGE))
    ],
    summary="上传并索引需求来源文档",
)
async def upload_requirement_source_document(
        project_id: int,
        current_user: CurrentUser,
        service: KnowledgeDocumentServiceDep,
        knowledge_base_id: Annotated[int, Form(gt=0)],
        file: Annotated[UploadFile, File(description="需要进行 AI 拆解的需求文档")],
        title: Annotated[str | None, Form()] = None,
        module_id: Annotated[int | None, Form()] = None,
        metadata: Annotated[str, Form()] = "{}",
) -> ApiResult[KnowledgeDocumentVO]:
    """上传需求来源文件，并自动提交解析和索引任务。

    功能：把新建需求弹窗中选择的文件保存为 REQUIREMENT 类型知识文档，随后
    立即把该文档交给 Celery 完成解析、切片、向量化和全文索引。

    作用：这是“直接上传需求文档”页面模式的后端入口。接口返回文档 ID 后，
    前端会把它写入 Requirement.document_id，从而自动建立需求与来源的关联。

    为什么用它：复用统一的知识文档上传、存储和索引 Service，避免需求模块
    再实现一套文件处理逻辑；同时只要求 requirement:manage 权限，使需求管理者
    不必额外获得整个知识文档管理页面的上传和索引按钮权限。
    """

    # 文档类型由业务入口固定为 REQUIREMENT，不能相信前端自由传值。
    payload = KnowledgeDocumentUploadDTO(
        title=title,
        document_type=KnowledgeDocumentType.REQUIREMENT,
        module_id=module_id,
        metadata=metadata,
    )
    document = await service.upload_knowledge_document(
        project_id=project_id,
        knowledge_base_id=knowledge_base_id,
        current_user=current_user,
        payload=payload,
        file=file,
    )

    # 上传仅创建 PENDING 记录；这里继续提交索引，用户无需再到知识文档页面
    # 手工点击“建立索引”。需求可以立即关联该 ID，但文档 READY 后才能 AI 拆解。
    indexed_document = await service.submit_index(
        project_id=project_id,
        knowledge_base_id=knowledge_base_id,
        document_id=document.id,
        current_user=current_user,
    )
    return success(indexed_document, "需求来源文档已上传，正在解析")

@router.get(
    "/{project_id}/{requirement_id}",
    response_model=ApiResult[RequirementDetailVO],
    dependencies=[
        Depends(
            require_permission(
                Permission.REQUIREMENT_VIEW
            )
        )
    ]
)
async def get_requirement_detail(
        project_id: int,
        requirement_id: int,
        current_user:CurrentUser,
        service:RequirementsServiceDep
)->ApiResult[RequirementDetailVO]:
    result = await service.get_requirement_detail(project_id,requirement_id,current_user)
    return success(result,"查询详情成功")

@router.post(
    "/{project_id}",
    response_model=ApiResult[RequirementVO],
    dependencies=[
        Depends(
            require_permission(Permission.REQUIREMENT_MANAGE)
        )
    ]
)
async def create_requirement(
        project_id: int,
        payload:RequirementCreateDTO,
        current_user:CurrentUser,
        service:RequirementsServiceDep
)-> ApiResult[RequirementVO]:
    result = await service.create_requirement(project_id,payload,current_user)
    return success(result,"添加成功")

@router.put(
    "/{project_id}/{requirement_id}",
    response_model=ApiResult[RequirementVO],
    dependencies=[
        Depends(
            require_permission(Permission.REQUIREMENT_MANAGE)
        )
    ]
)
async def update_requirement(
        project_id: int,
        requirement_id: int,
        payload:RequirementUpdateDTO,
        current_user:CurrentUser,
        service:RequirementsServiceDep
)->ApiResult[RequirementVO]:
    result = await service.update_requirement(project_id,requirement_id,payload,current_user)
    return success(result,"更新成功")

@router.delete(
    "/{project_id}/{requirement_id}",
    response_model=ApiResult[None],
    dependencies=[
        Depends(
            require_permission(
                Permission.REQUIREMENT_MANAGE
            )
        )
    ]
)
async def delete_requirement(
        project_id: int,
        requirement_id: int,
        current_user:CurrentUser,
        service:RequirementsServiceDep
)->ApiResult[None]:
    await service.delete_requirement(project_id,requirement_id,current_user)
    return success(message="删除成功")
