"""测试工具目录、外部连接、文件模板、任务和审批 API。"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.service_deps.tool_center import (
    ToolCenterServiceDep,
    ToolExecutionServiceDep,
)
from app.core.constants import ToolTaskStatus, ToolTaskType
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.exceptions import BadRequestException
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.tool_center import (
    ExternalConnectionCreateDTO,
    ExternalConnectionUpdateDTO,
    FileTemplateCreateDTO,
    FileTemplateUpdateDTO,
    ToolApprovalDTO,
    ToolTaskCreateDTO,
    ToolTaskQueryDTO,
)
from app.schemas.vo.tool_center import ExternalConnectionVO, FileTemplateVO, ToolDefinitionVO, ToolTaskVO

router = APIRouter(tags=["测试工具中心"])


@router.get(
    "/tools",
    response_model=ApiResult[list[ToolDefinitionVO]],
    dependencies=[Depends(require_permission(Permission.TOOL_VIEW))],
)
async def list_tools(_: CurrentUser, service: ToolCenterServiceDep) -> ApiResult[list[ToolDefinitionVO]]:
    """查看服务器注册的受控工具目录。"""
    return success(await service.list_tools())


@router.get(
    "/projects/{project_id}/connections",
    response_model=ApiResult[list[ExternalConnectionVO]],
    dependencies=[Depends(require_permission(Permission.TOOL_VIEW))],
)
async def list_connections(
    current_user: CurrentUser, service: ToolCenterServiceDep, project_id: int = Path(gt=0)
) -> ApiResult[list[ExternalConnectionVO]]:
    return success(await service.list_connections(project_id, current_user))


@router.post(
    "/projects/{project_id}/connections",
    response_model=ApiResult[ExternalConnectionVO],
    dependencies=[Depends(require_permission(Permission.TOOL_MANAGE))],
)
async def create_connection(
    payload: ExternalConnectionCreateDTO,
    current_user: CurrentUser,
    service: ToolCenterServiceDep,
    project_id: int = Path(gt=0),
) -> ApiResult[ExternalConnectionVO]:
    return success(await service.create_connection(project_id, payload, current_user), "外部连接创建成功")


@router.put(
    "/projects/{project_id}/connections/{connection_id}",
    response_model=ApiResult[ExternalConnectionVO],
    dependencies=[Depends(require_permission(Permission.TOOL_MANAGE))],
)
async def update_connection(
    payload: ExternalConnectionUpdateDTO,
    current_user: CurrentUser,
    service: ToolCenterServiceDep,
    project_id: int = Path(gt=0),
    connection_id: int = Path(gt=0),
) -> ApiResult[ExternalConnectionVO]:
    return success(
        await service.update_connection(project_id, connection_id, payload, current_user), "外部连接更新成功"
    )


@router.delete(
    "/projects/{project_id}/connections/{connection_id}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(Permission.TOOL_MANAGE))],
)
async def delete_connection(
    current_user: CurrentUser,
    service: ToolCenterServiceDep,
    project_id: int = Path(gt=0),
    connection_id: int = Path(gt=0),
) -> ApiResult[None]:
    await service.delete_connection(project_id, connection_id, current_user)
    return success(message="外部连接删除成功")


@router.get(
    "/projects/{project_id}/file-templates",
    response_model=ApiResult[list[FileTemplateVO]],
    dependencies=[Depends(require_permission(Permission.TOOL_VIEW))],
)
async def list_file_templates(
    current_user: CurrentUser, service: ToolCenterServiceDep, project_id: int = Path(gt=0)
) -> ApiResult[list[FileTemplateVO]]:
    return success(await service.list_templates(project_id, current_user))


@router.post(
    "/projects/{project_id}/file-templates",
    response_model=ApiResult[FileTemplateVO],
    dependencies=[Depends(require_permission(Permission.TOOL_MANAGE))],
)
async def create_file_template(
    payload: FileTemplateCreateDTO,
    current_user: CurrentUser,
    service: ToolCenterServiceDep,
    project_id: int = Path(gt=0),
) -> ApiResult[FileTemplateVO]:
    return success(await service.create_template(project_id, payload, current_user), "文件模板创建成功")


@router.put(
    "/projects/{project_id}/file-templates/{template_id}",
    response_model=ApiResult[FileTemplateVO],
    dependencies=[Depends(require_permission(Permission.TOOL_MANAGE))],
)
async def update_file_template(
    payload: FileTemplateUpdateDTO,
    current_user: CurrentUser,
    service: ToolCenterServiceDep,
    project_id: int = Path(gt=0),
    template_id: int = Path(gt=0),
) -> ApiResult[FileTemplateVO]:
    return success(await service.update_template(project_id, template_id, payload, current_user), "文件模板更新成功")


@router.post(
    "/projects/{project_id}/tool-tasks",
    response_model=ApiResult[ToolTaskVO],
    dependencies=[Depends(require_permission(Permission.TOOL_MANAGE))],
)
async def create_tool_task(
    payload: ToolTaskCreateDTO, current_user: CurrentUser, service: ToolCenterServiceDep, project_id: int = Path(gt=0)
) -> ApiResult[ToolTaskVO]:
    return success(await service.create_task(project_id, payload, current_user), "工具任务创建成功")


@router.get(
    "/projects/{project_id}/tool-tasks",
    response_model=ApiResult[PageResult[ToolTaskVO]],
    dependencies=[Depends(require_permission(Permission.TOOL_VIEW))],
)
async def list_tool_tasks(
    current_user: CurrentUser,
    service: ToolCenterServiceDep,
    project_id: int = Path(gt=0),
    status: Annotated[ToolTaskStatus | None, Query()] = None,
    task_type: Annotated[ToolTaskType | None, Query()] = None,
    current: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResult[PageResult[ToolTaskVO]]:
    query = ToolTaskQueryDTO(status=status, task_type=task_type, current=current, size=size)
    return success(await service.list_tasks(project_id, query, current_user))


@router.get(
    "/projects/{project_id}/tool-tasks/{task_id}",
    response_model=ApiResult[ToolTaskVO],
    dependencies=[Depends(require_permission(Permission.TOOL_VIEW))],
)
async def get_tool_task(
    current_user: CurrentUser, service: ToolCenterServiceDep, project_id: int = Path(gt=0), task_id: int = Path(gt=0)
) -> ApiResult[ToolTaskVO]:
    return success(await service.get_task(project_id, task_id, current_user))


@router.post(
    "/projects/{project_id}/tool-tasks/{task_id}/approval",
    response_model=ApiResult[ToolTaskVO],
    dependencies=[Depends(require_permission(Permission.TOOL_APPROVE))],
)
async def approve_tool_task(
    payload: ToolApprovalDTO,
    current_user: CurrentUser,
    service: ToolCenterServiceDep,
    project_id: int = Path(gt=0),
    task_id: int = Path(gt=0),
) -> ApiResult[ToolTaskVO]:
    return success(await service.approve_task(project_id, task_id, payload, current_user), "审批结果已保存")


@router.post(
    "/projects/{project_id}/tool-tasks/{task_id}/preview",
    response_model=ApiResult[ToolTaskVO],
    dependencies=[Depends(require_permission(Permission.TOOL_PREVIEW))],
)
async def preview_tool_task(
    current_user: CurrentUser,
    service: ToolExecutionServiceDep,
    project_id: int = Path(gt=0),
    task_id: int = Path(gt=0),
) -> ApiResult[ToolTaskVO]:
    """由服务器读取真实外部状态并生成不可伪造的预览。"""
    return success(await service.preview(project_id, task_id, current_user))


@router.post(
    "/projects/{project_id}/tool-tasks/{task_id}/input-file",
    response_model=ApiResult[ToolTaskVO],
    dependencies=[Depends(require_permission(Permission.TOOL_MANAGE))],
)
async def upload_tool_input_file(
    file: UploadFile,
    current_user: CurrentUser,
    service: ToolExecutionServiceDep,
    project_id: int = Path(gt=0),
    task_id: int = Path(gt=0),
) -> ApiResult[ToolTaskVO]:
    """为文件校验任务上传输入文件；按块读取并限制 50MB。"""
    content = bytearray()
    while chunk := await file.read(1024 * 1024):
        content.extend(chunk)
        if len(content) > 50 * 1024 * 1024:
            raise BadRequestException("校验文件不能超过 50MB")
    return success(
        await service.attach_input_file(
            project_id,
            task_id,
            file.filename or "input.dat",
            file.content_type or "application/octet-stream",
            bytes(content),
            current_user,
        )
    )


@router.post(
    "/projects/{project_id}/tool-tasks/{task_id}/execute",
    response_model=ApiResult[ToolTaskVO],
    dependencies=[Depends(require_permission(Permission.TOOL_EXECUTE))],
)
async def execute_tool_task(
    current_user: CurrentUser,
    service: ToolExecutionServiceDep,
    project_id: int = Path(gt=0),
    task_id: int = Path(gt=0),
) -> ApiResult[ToolTaskVO]:
    """执行已预览且满足审批条件的固定工具任务。"""
    return success(await service.execute(project_id, task_id, current_user))


@router.post(
    "/projects/{project_id}/tool-tasks/{task_id}/rollback",
    response_model=ApiResult[ToolTaskVO],
    dependencies=[Depends(require_permission(Permission.TOOL_ROLLBACK))],
)
async def rollback_tool_task(
    current_user: CurrentUser,
    service: ToolExecutionServiceDep,
    project_id: int = Path(gt=0),
    task_id: int = Path(gt=0),
) -> ApiResult[ToolTaskVO]:
    """使用任务保存的执行前备份回滚受支持的外部操作。"""
    return success(await service.rollback(project_id, task_id, current_user))


@router.get(
    "/projects/{project_id}/tool-tasks/{task_id}/artifacts/{artifact_id}",
    dependencies=[Depends(require_permission(Permission.TOOL_VIEW))],
)
async def download_tool_artifact(
    current_user: CurrentUser,
    service: ToolExecutionServiceDep,
    project_id: int = Path(gt=0),
    task_id: int = Path(gt=0),
    artifact_id: int = Path(gt=0),
) -> StreamingResponse:
    """流式下载任务产物，接口不暴露底层对象键。"""
    artifact = await service.get_artifact(
        project_id,
        task_id,
        artifact_id,
        current_user,
    )
    filename = quote(artifact.name)
    return StreamingResponse(
        service.storage.stream_file(artifact.object_key),
        media_type=artifact.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
