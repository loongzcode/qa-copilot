"""测试用例发布前的接口自动化就绪校验。"""

from types import SimpleNamespace

import pytest
from app.agents.case_generation_schemas import GeneratedTestCase
from app.automation.definition_factory import (
    build_automation_definition_from_test_case,
)
from app.core.constants import CaseReviewAction
from app.core.constants import TestCaseStatus as CaseStatus
from app.exceptions import BadRequestException
from app.models import TestCase as CaseEntity
from app.models import TestCaseStep as CaseStepEntity
from app.schemas.dto.test_cases import CaseReviewDTO
from app.services.test_cases_service import TestCasesService as CasesService


def _test_case(*, case_type: str, automatable: bool, test_data: object | None) -> CaseEntity:
    """构造一条进入发布审核前的最小用例实体。"""
    test_case = CaseEntity(
        id=9,
        project_id=8,
        module_id=None,
        case_code="CASE-9",
        title="文章查询",
        case_type=case_type,
        priority="P1",
        preconditions="用户已登录",
        expected_summary="查询成功",
        status=CaseStatus.APPROVED.value,
        source="MANUAL",
        automatable=automatable,
        version=1,
        case_metadata={},
        created_by=1,
        updated_by=1,
    )
    test_case.steps = [
        CaseStepEntity(
            id=90,
            test_case_id=9,
            step_no=1,
            action="查询文章",
            test_data=test_data,
            expected_result="返回文章列表",
        )
    ]
    return test_case


def test_generated_non_api_case_cannot_keep_automatable_flag() -> None:
    """模型误把非接口用例标为可自动化时，应在落库前自动纠正。"""
    generated = GeneratedTestCase.model_validate(
        {
            "local_id": "case-1",
            "title": "文章页面测试",
            "case_type": "OTHER",
            "priority": "P1",
            "automatable": True,
            "requirement_item_ids": [1],
            "generation_reason": "覆盖需求",
            "confidence": 0.9,
            "steps": [
                {
                    "step_no": 1,
                    "action": "打开页面",
                    "expected_result": "页面展示成功",
                }
            ],
        }
    )

    assert generated.automatable is False


def test_definition_factory_explains_how_to_fix_missing_protocol() -> None:
    """缺少结构化步骤时，错误必须告诉用户去哪里、补什么。"""
    test_case = _test_case(case_type="API", automatable=True, test_data=None)

    with pytest.raises(BadRequestException, match="填入接口模板"):
        build_automation_definition_from_test_case(test_case)


@pytest.mark.asyncio
async def test_publish_rejects_contradictory_automatable_case_type() -> None:
    """OTHER 与 automatable=True 的矛盾用例不得再被直接发布。"""
    service = CasesService(
        repository=SimpleNamespace(),
        project_repository=SimpleNamespace(),
        module_repository=SimpleNamespace(),
        requirement_repository=SimpleNamespace(),
        coverage_service=SimpleNamespace(),
    )
    test_case = _test_case(case_type="OTHER", automatable=True, test_data=None)

    with pytest.raises(BadRequestException, match="测试类型不是“接口测试”"):
        await service._apply_review_action(
            project_id=8,
            test_case=test_case,
            payload=CaseReviewDTO(action=CaseReviewAction.PUBLISH, comment=""),
            current_user=SimpleNamespace(id=1),
        )
