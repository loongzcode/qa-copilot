"""测试用例批量审核入口的边界与事务行为。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.api.test_cases_api import router
from app.core.constants import CaseReviewAction
from app.exceptions.exception_business import BadRequestException
from app.schemas.dto.test_cases import CaseBatchReviewDTO
from app.services.test_cases_service import TestCasesService as CasesService
from pydantic import ValidationError


def test_batch_review_dto_accepts_safe_action_and_camel_case_ids() -> None:
    """前端使用 camelCase 传多个唯一 ID 时应成功解析。"""
    payload = CaseBatchReviewDTO.model_validate(
        {
            "testCaseIds": [3, 5],
            "action": "PUBLISH",
            "comment": "统一发布",
        }
    )

    assert payload.test_case_ids == [3, 5]
    assert payload.action == CaseReviewAction.PUBLISH


@pytest.mark.parametrize(
    ("test_case_ids", "action"),
    [
        ([3, 3], "ACCEPT"),
        ([3], "MODIFY"),
        ([3], "DUPLICATE"),
    ],
)
def test_batch_review_dto_rejects_duplicates_and_case_specific_actions(
    test_case_ids: list[int],
    action: str,
) -> None:
    """重复 ID、修改和判重不能进入批量状态机。"""
    with pytest.raises(ValidationError):
        CaseBatchReviewDTO.model_validate(
            {
                "testCaseIds": test_case_ids,
                "action": action,
                "comment": "",
            }
        )


def test_batch_route_is_registered_before_dynamic_detail_route() -> None:
    """固定批量路径必须先匹配，不能被动态整数路径提前截获。"""
    route_paths = [route.path for route in router.routes]

    assert route_paths.index("/test_cases/batch-review/{project_id}") < route_paths.index(
        "/test_cases/{project_id}/{test_case_id}"
    )
    assert "/test_cases/{project_id}/{test_case_id}/clone-draft" in route_paths


@pytest.mark.asyncio
async def test_batch_review_rolls_back_when_any_case_fails() -> None:
    """批量中的任意一条失败时，不得提交前面已经应用的状态变化。"""
    repository = SimpleNamespace(
        get_test_cases_for_review=AsyncMock(
            return_value=[SimpleNamespace(id=1), SimpleNamespace(id=2)]
        ),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    service = CasesService(
        repository=repository,
        project_repository=SimpleNamespace(),
        module_repository=SimpleNamespace(),
        requirement_repository=SimpleNamespace(),
        coverage_service=SimpleNamespace(),
    )
    service._require_project = AsyncMock()  # type: ignore[method-assign]
    service._apply_review_action = AsyncMock(  # type: ignore[method-assign]
        side_effect=[None, BadRequestException("第二条状态不允许")]
    )
    payload = CaseBatchReviewDTO(
        test_case_ids=[1, 2],
        action=CaseReviewAction.ACCEPT,
        comment="",
    )

    with pytest.raises(BadRequestException):
        await service.batch_review_test_cases(
            project_id=8,
            payload=payload,
            current_user=SimpleNamespace(id=9),
        )

    repository.commit.assert_not_awaited()
    repository.rollback.assert_awaited_once()
