"""测试用例管理、覆盖分析、缺失生成和审核接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.service_deps.test_cases import TestCasesServiceDep
from app.core.constants import CaseGenerationTaskStatus, TestCaseSource, TestCaseStatus
from app.core.deps import CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.dto.test_cases import (
    CaseBatchReviewDTO,
    CaseReviewDTO,
    TestCaseCreateDTO,
)
from app.schemas.vo.test_cases import (
    CaseGenerationTaskVO,
    CoverageMatrixVO,
    TestCaseRequirementItemOptionVO,
    TestCaseVO,
)

router = APIRouter(prefix="/test_cases", tags=["测试用例管理"])
requirement_case_router = APIRouter(
    prefix="/requirements",
    tags=["需求覆盖与用例生成"],
)


@router.get(
    "/{project_id}",
    response_model=ApiResult[PageResult[TestCaseVO]],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_VIEW))],
)
async def list_test_cases(
    project_id: int,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
    keyword: Annotated[str, Query(max_length=300)] = "",
    module_id: Annotated[int | None, Query(gt=0)] = None,
    status: Annotated[TestCaseStatus | None, Query()] = None,
    source: Annotated[TestCaseSource | None, Query()] = None,
    current: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
) -> ApiResult[PageResult[TestCaseVO]]:
    """分页查询项目测试用例和完整步骤摘要。"""
    records, total = await service.list_test_cases(
        project_id,
        current_user,
        keyword,
        module_id,
        status,
        source,
        current,
        size,
    )
    return success(
        PageResult(
            current=current,
            size=size,
            total=total,
            records=records,
        )
    )


@router.post(
    "/{project_id}",
    response_model=ApiResult[TestCaseVO],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_MANAGE))],
)
async def create_test_case(
    project_id: int,
    payload: TestCaseCreateDTO,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
) -> ApiResult[TestCaseVO]:
    """创建一条人工测试用例。"""
    return success(
        await service.create_test_case(project_id, payload, current_user),
        "测试用例创建成功",
    )


# 固定路径必须放在 /{project_id}/{test_case_id} 之前，避免 generation-tasks
# 被当成整数 test_case_id 匹配后产生 422。
@router.get(
    "/{project_id}/generation-tasks",
    response_model=ApiResult[PageResult[CaseGenerationTaskVO]],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_VIEW))],
)
async def list_generation_tasks(
    project_id: int,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
    requirement_id: Annotated[int | None, Query(gt=0)] = None,
    status: Annotated[CaseGenerationTaskStatus | None, Query()] = None,
    current: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
) -> ApiResult[PageResult[CaseGenerationTaskVO]]:
    """分页查询缺失用例生成任务和对应草稿。"""
    records, total = await service.list_generation_tasks(
        project_id,
        current_user,
        requirement_id,
        status,
        current,
        size,
    )
    return success(PageResult(current=current, size=size, total=total, records=records))


@router.get(
    "/{project_id}/requirement-item-options",
    response_model=ApiResult[list[TestCaseRequirementItemOptionVO]],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_VIEW))],
)
async def list_requirement_item_options(
    project_id: int,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
) -> ApiResult[list[TestCaseRequirementItemOptionVO]]:
    """查询项目下可供用例关联的已确认需求点。"""
    return success(
        await service.list_requirement_item_options(project_id, current_user)
    )


@router.post(
    "/batch-review/{project_id}",
    response_model=ApiResult[list[TestCaseVO]],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_REVIEW))],
)
async def batch_review_test_cases(
    project_id: int,
    payload: CaseBatchReviewDTO,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
) -> ApiResult[list[TestCaseVO]]:
    """在一个事务中批量接受、驳回或发布测试用例。"""
    return success(
        await service.batch_review_test_cases(
            project_id,
            payload,
            current_user,
        ),
        f"已批量处理 {len(payload.test_case_ids)} 条测试用例",
    )


@router.get(
    "/{project_id}/{test_case_id}",
    response_model=ApiResult[TestCaseVO],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_VIEW))],
)
async def get_test_case(
    project_id: int,
    test_case_id: int,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
) -> ApiResult[TestCaseVO]:
    """查询测试用例详情。"""
    return success(await service.get_test_case(project_id, test_case_id, current_user))


@router.put(
    "/{project_id}/{test_case_id}",
    response_model=ApiResult[TestCaseVO],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_MANAGE))],
)
async def update_test_case(
    project_id: int,
    test_case_id: int,
    payload: TestCaseCreateDTO,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
) -> ApiResult[TestCaseVO]:
    """整体更新测试用例、步骤和需求点关联。"""
    return success(
        await service.update_test_case(
            project_id,
            test_case_id,
            payload,
            current_user,
        ),
        "测试用例更新成功",
    )


@router.post(
    "/{project_id}/{test_case_id}/clone-draft",
    response_model=ApiResult[TestCaseVO],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_MANAGE))],
)
async def clone_test_case_as_draft(
    project_id: int,
    test_case_id: int,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
) -> ApiResult[TestCaseVO]:
    """把不可直接修改的发布版本复制为可编辑草稿。"""
    return success(
        await service.clone_test_case_as_draft(
            project_id,
            test_case_id,
            current_user,
        ),
        "已创建可编辑的新版本草稿",
    )


@router.delete(
    "/{project_id}/{test_case_id}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_MANAGE))],
)
async def delete_test_case(
    project_id: int,
    test_case_id: int,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
) -> ApiResult[None]:
    """软删除未发布测试用例。"""
    await service.delete_test_case(project_id, test_case_id, current_user)
    return success(message="测试用例删除成功")


@router.post(
    "/{project_id}/{test_case_id}/review",
    response_model=ApiResult[TestCaseVO],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_REVIEW))],
)
async def review_test_case(
    project_id: int,
    test_case_id: int,
    payload: CaseReviewDTO,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
) -> ApiResult[TestCaseVO]:
    """执行接受、修改、驳回、判重、发布或停用动作。"""
    return success(
        await service.review_test_case(
            project_id,
            test_case_id,
            payload,
            current_user,
        ),
        "审核结果已保存",
    )


@requirement_case_router.get(
    "/{project_id}/{requirement_id}/coverage",
    response_model=ApiResult[CoverageMatrixVO],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_VIEW))],
)
async def get_coverage_matrix(
    project_id: int,
    requirement_id: int,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
) -> ApiResult[CoverageMatrixVO]:
    """查询当前已保存的需求覆盖矩阵。"""
    return success(
        await service.get_coverage_matrix(project_id, requirement_id, current_user)
    )


@requirement_case_router.post(
    "/{project_id}/{requirement_id}/coverage",
    response_model=ApiResult[CoverageMatrixVO],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_GENERATE))],
)
async def analyze_coverage(
    project_id: int,
    requirement_id: int,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
) -> ApiResult[CoverageMatrixVO]:
    """重新检索标准用例并计算覆盖关系。"""
    return success(
        await service.analyze_coverage(project_id, requirement_id, current_user),
        "覆盖分析完成",
    )


@requirement_case_router.post(
    "/{project_id}/{requirement_id}/generate-cases",
    response_model=ApiResult[CaseGenerationTaskVO],
    dependencies=[Depends(require_permission(Permission.TEST_CASE_GENERATE))],
)
async def generate_missing_cases(
    project_id: int,
    requirement_id: int,
    current_user: CurrentUser,
    service: TestCasesServiceDep,
) -> ApiResult[CaseGenerationTaskVO]:
    """只针对部分覆盖和未覆盖需求点提交异步生成任务。"""
    return success(
        await service.submit_generation(project_id, requirement_id, current_user),
        "用例生成任务已提交",
    )
