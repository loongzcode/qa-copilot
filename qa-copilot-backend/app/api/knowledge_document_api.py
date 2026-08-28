from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from starlette.responses import StreamingResponse

from app.api.service_deps.knowledge_document import KnowledgeDocumentServiceDep
from app.core.constants import KnowledgeDocumentParseStatus, KnowledgeDocumentType
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.knowledge_documents import KnowledgeDocumentUploadDTO
from app.schemas.vo.knowledge_documents import KnowledgeDocumentVO

router = APIRouter(prefix="/knowledge-document", tags=["知识库文档管理"])


@router.get("/{project_id}/bases/{knowledge_base_id}/documents",
            response_model=ApiResult[PageResult[KnowledgeDocumentVO]],
            dependencies=[Depends(require_permission(Permission.KNOWLEDGE_DOCUMENT_VIEW))],
            summary="查询知识库文档")
async def get_knowledge_documents(
        project_id: int,
        knowledge_base_id: int,
        current_user: CurrentUser,
        service: KnowledgeDocumentServiceDep,
        document_type: KnowledgeDocumentType | None = None,
        parse_status: KnowledgeDocumentParseStatus | None = None,
        module_id: int | None = None,
        current: int = Query(default=1, ge=1),
        size: int = Query(default=10, ge=1, le=100),
        keyword: str = "",
) -> ApiResult[PageResult[KnowledgeDocumentVO]]:
    records, total = await service.list_knowledge_documents(project_id, knowledge_base_id, current_user,
                                                            document_type, parse_status, module_id,
                                                            current, size, keyword)
    return success(PageResult(current=current, total=total, records=records, size=size))


@router.post(
    "/{project_id}/bases/{knowledge_base_id}/documents",
    response_model=ApiResult[KnowledgeDocumentVO],
    dependencies=[
        Depends(require_permission(Permission.KNOWLEDGE_DOCUMENT_UPLOAD))
    ],
    summary="上传知识库文档",
)
async def upload_knowledge_document(
        project_id: int,
        knowledge_base_id: int,
        current_user: CurrentUser,
        service: KnowledgeDocumentServiceDep,
        document_type: Annotated[KnowledgeDocumentType, Form()],
        file: Annotated[UploadFile, File(description="需要上传的知识文档")],
        title: Annotated[str | None, Form()] = None,
        module_id: Annotated[int | None, Form()] = None,
        metadata: Annotated[str, Form()] = "{}",
) -> ApiResult[KnowledgeDocumentVO]:
    """接收 multipart/form-data 文件及文档业务参数。"""

    # 1. 这个接口同时接收两部分 multipart/form-data 数据：
    #    - payload：标题、文档类型、关联模块和 metadata；
    #    - file：PDF、DOCX、Markdown 或 TXT 文件本身。
    #    FastAPI 会通过 Form() 把普通表单字段组装成 DTO，
    #    通过 File() 把上传内容转换成 UploadFile。

    # 2. 调用 service.upload_document()，按下面顺序传入：
    #    project_id、knowledge_base_id、current_user、payload、file。
    #    文件格式、大小、知识库数据权限、模块归属、SHA-256 去重、
    #    文件存储和数据库事务都属于业务规则，应放在 Service 中处理。
    payload = KnowledgeDocumentUploadDTO(
        title=title,
        document_type=document_type,
        module_id=module_id,
        metadata=metadata,
    )
    knowledge_document = await service.upload_knowledge_document(
        project_id=project_id,
        knowledge_base_id=knowledge_base_id,
        current_user=current_user,
        payload=payload,
        file=file,
    )
    # 3. Service 返回 KnowledgeDocumentVO 后，使用 success() 包装并返回。
    return success(knowledge_document, "上传文档成功")


@router.post(
    "/{project_id}/bases/{knowledge_base_id}/documents/{document_id}/index",
    response_model=ApiResult[KnowledgeDocumentVO],
    dependencies=[
        Depends(require_permission(Permission.KNOWLEDGE_DOCUMENT_INDEX))
    ],
    summary="提交知识文档索引任务",
)
async def index_knowledge_document(
        project_id: int,
        knowledge_base_id: int,
        document_id: int,
        current_user: CurrentUser,
        service: KnowledgeDocumentServiceDep,
) -> ApiResult[KnowledgeDocumentVO]:
    """首次索引、重新索引和失败重试统一使用该接口。"""

    document = await service.submit_index(
        project_id=project_id,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
        current_user=current_user,
    )
    return success(document, "索引任务已提交")


@router.delete(
    "/{project_id}/bases/{knowledge_base_id}/documents/{document_id}",
    response_model=ApiResult[None],
    dependencies=[
        Depends(require_permission(Permission.KNOWLEDGE_DOCUMENT_MANAGE))
    ],
    summary="删除知识库文档",
)
async def delete_knowledge_document(
        project_id: int,
        knowledge_base_id: int,
        document_id: int,
        current_user: CurrentUser,
        service: KnowledgeDocumentServiceDep,
) -> ApiResult[None]:
    """软删除文档、立即清理检索切片，并异步删除原始存储文件。"""

    await service.delete_knowledge_document(
        project_id=project_id,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
        current_user=current_user,
    )
    return success(message="知识文档删除成功")


@router.get(
    "/{project_id}/bases/{knowledge_base_id}/documents/{document_id}/preview",
    response_class=StreamingResponse,
    dependencies=[
        Depends(
            require_permission(
                Permission.KNOWLEDGE_DOCUMENT_VIEW
            )

        )
    ]
)
async def preview_document(
        project_id: int,
        knowledge_base_id: int,
        document_id: int,
        current_user: CurrentUser,
        service: KnowledgeDocumentServiceDep
) -> StreamingResponse:
    preview = await service.preview_document(
        project_id,
        knowledge_base_id,
        document_id,
        current_user
    )
    return StreamingResponse(
        content=preview.content,
        media_type=preview.mime_type,
        headers={
            "Content-Disposition": (
                "inline; "
                f"filename*=UTF-8''{quote(preview.filename, safe='')}"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
