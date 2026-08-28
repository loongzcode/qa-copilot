from fastapi import APIRouter, Depends, Query

from app.api.service_deps.test_project_members import TestProjectMembersServiceDep
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.test_project_member import TestProjectMemberCreateDTO, TestProjectMemberUpdateDTO
from app.schemas.vo.test_project_member import TestProjectMemberOptionVO, TestProjectMemberVO

router = APIRouter(prefix="/test-projects", tags=["项目成员管理"])


@router.get(
    "/{project_id}/members",
    response_model=ApiResult[PageResult[TestProjectMemberVO]],
    dependencies=[Depends(dependency=require_permission(code=Permission.PROJECT_MEMBER_VIEW))],
    summary="查询项目成员列表",
)
async def get_members(
    project_id: int,
    current_user: CurrentUser,
    service: TestProjectMembersServiceDep,
    current: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    keyword: str = "",
) -> ApiResult[PageResult[TestProjectMemberVO]]:
    records, total = await service.list_members(
        project_id,
        current_user,
        current,
        size,
        keyword,
    )
    return success(PageResult(current=current, total=total, records=records, size=size))


@router.post(
    "/{project_id}/members",
    response_model=ApiResult[TestProjectMemberVO],
    dependencies=[Depends(dependency=require_permission(code=Permission.PROJECT_MEMBER_MANAGE))],
    summary="添加项目成功",
)
async def create_member(
    project_id: int,
    payload: TestProjectMemberCreateDTO,
    current_user: CurrentUser,
    service: TestProjectMembersServiceDep,
) -> ApiResult[TestProjectMemberVO]:
    member = await service.create_member(
        project_id,
        current_user,
        payload,
    )
    return success(member, "添加成功")


@router.put(
    "/{project_id}/members/{user_id}",
    response_model=ApiResult[TestProjectMemberVO],
    dependencies=[Depends(require_permission(code=Permission.PROJECT_MEMBER_MANAGE))],
    summary="修改项目成员角色"
)
async def update_member(
        project_id: int,
        payload: TestProjectMemberUpdateDTO,
        user_id: int,
        current_user: CurrentUser,
        service: TestProjectMembersServiceDep,
)->ApiResult[TestProjectMemberVO]:
    member = await service.update_member(
        project_id,
        user_id,
        payload,
        current_user,
    )
    return success(member, "成员角色修改成功")

@router.delete(
    "/{project_id}/members/{user_id}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(code=Permission.PROJECT_MEMBER_MANAGE))],
    summary="删除项目成员"
)
async def delete_member(
        project_id: int,
        user_id: int,
        current_user: CurrentUser,
        service: TestProjectMembersServiceDep,
)->ApiResult[None]:
    await service.remove_member(
        project_id,
        user_id,
        current_user,
    )
    return success(message="项目成员移除成功")


@router.get("/{project_id}/member-options",
            response_model=ApiResult[list[TestProjectMemberOptionVO]],
            dependencies=[Depends(require_permission(code=Permission.PROJECT_MEMBER_MANAGE))],)
async def get_member_options(
        project_id: int,
        current_user: CurrentUser,
        service: TestProjectMembersServiceDep,
        keyword: str = "",
        limit: int = Query(20, ge=1, le=100),
) -> ApiResult[list[TestProjectMemberOptionVO]]:
    options = await service.list_member_options(
        project_id,
        current_user,
        keyword,
        limit,
    )
    return success(options)
