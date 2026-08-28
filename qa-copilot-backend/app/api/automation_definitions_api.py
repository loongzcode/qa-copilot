"""受控接口自动化定义的管理接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.service_deps.automation_definitions import (
    AutomationDefinitionsServiceDep,
)
from app.core.constants import AutomationDefinitionStatus
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.automation_definitions import AutomationDefinitionUpdateDTO
from app.schemas.vo.automation_definitions import AutomationDefinitionChangeVO, AutomationDefinitionVO

router = APIRouter(prefix="/automation-definitions", tags=["自动化测试定义"])


@router.get(
    "/{project_id}",
    response_model=ApiResult[PageResult[AutomationDefinitionVO]],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_VIEW))],
)
async def list_automation_definitions(
    project_id: int,
    current_user: CurrentUser,
    service: AutomationDefinitionsServiceDep,
    keyword: Annotated[str, Query(max_length=300)] = "",
    status: Annotated[AutomationDefinitionStatus | None, Query()] = None,
    current: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
) -> ApiResult[PageResult[AutomationDefinitionVO]]:
    """分页查询项目自动化定义。"""
    records, total = await service.list_definitions(
        project_id,
        current_user,
        keyword,
        status,
        current,
        size,
    )
    return success(PageResult(current=current, size=size, total=total, records=records))


@router.get(
    "/{project_id}/{definition_id}",
    response_model=ApiResult[AutomationDefinitionVO],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_VIEW))],
)
async def get_automation_definition(
    project_id: int,
    definition_id: int,
    current_user: CurrentUser,
    service: AutomationDefinitionsServiceDep,
) -> ApiResult[AutomationDefinitionVO]:
    """查询一条定义的完整受控 JSON。"""
    return success(await service.get_definition(project_id, definition_id, current_user))


@router.get(
    "/{project_id}/{definition_id}/changes",
    response_model=ApiResult[list[AutomationDefinitionChangeVO]],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_VIEW))],
)
async def list_automation_definition_changes(
    project_id: int,
    definition_id: int,
    current_user: CurrentUser,
    service: AutomationDefinitionsServiceDep,
) -> ApiResult[list[AutomationDefinitionChangeVO]]:
    """查询一条自动化定义从创建至今的完整变更链。"""
    return success(await service.list_definition_changes(project_id, definition_id, current_user))


@router.post(
    "/{project_id}/from-test-case/{test_case_id}",
    response_model=ApiResult[AutomationDefinitionVO],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_DEFINITION_MANAGE))],
)
async def create_automation_definition_from_test_case(
    project_id: int,
    test_case_id: int,
    current_user: CurrentUser,
    service: AutomationDefinitionsServiceDep,
) -> ApiResult[AutomationDefinitionVO]:
    """把符合条件的发布用例确定性转换为一个新草稿版本。"""
    return success(
        await service.create_from_test_case(project_id, test_case_id, current_user),
        "自动化定义草稿已创建",
    )


@router.put(
    "/{project_id}/{definition_id}",
    response_model=ApiResult[AutomationDefinitionVO],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_DEFINITION_MANAGE))],
)
async def update_automation_definition(
    project_id: int,
    definition_id: int,
    payload: AutomationDefinitionUpdateDTO,
    current_user: CurrentUser,
    service: AutomationDefinitionsServiceDep,
) -> ApiResult[AutomationDefinitionVO]:
    """编辑草稿定义，协议安全校验由 DTO 在进入 Service 前完成。"""
    return success(
        await service.update_definition(
            project_id,
            definition_id,
            payload,
            current_user,
        ),
        "自动化定义已保存",
    )


@router.post(
    "/{project_id}/{definition_id}/approve",
    response_model=ApiResult[AutomationDefinitionVO],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_DEFINITION_APPROVE))],
)
async def approve_automation_definition(
    project_id: int,
    definition_id: int,
    current_user: CurrentUser,
    service: AutomationDefinitionsServiceDep,
) -> ApiResult[AutomationDefinitionVO]:
    """审批草稿，并自动退出同一用例原来的已审批版本。"""
    return success(
        await service.approve_definition(project_id, definition_id, current_user),
        "自动化定义审批成功",
    )


@router.post(
    "/{project_id}/{definition_id}/retire",
    response_model=ApiResult[AutomationDefinitionVO],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_DEFINITION_APPROVE))],
)
async def retire_automation_definition(
    project_id: int,
    definition_id: int,
    current_user: CurrentUser,
    service: AutomationDefinitionsServiceDep,
) -> ApiResult[AutomationDefinitionVO]:
    """让当前审批版本退出后续执行候选。"""
    return success(
        await service.retire_definition(project_id, definition_id, current_user),
        "自动化定义已退出使用",
    )


@router.delete(
    "/{project_id}/{definition_id}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(Permission.AUTOMATION_DEFINITION_MANAGE))],
)
async def delete_automation_definition(
    project_id: int,
    definition_id: int,
    current_user: CurrentUser,
    service: AutomationDefinitionsServiceDep,
) -> ApiResult[None]:
    """软删除草稿或已退出定义。"""
    await service.delete_definition(project_id, definition_id, current_user)
    return success(message="自动化定义已删除")
