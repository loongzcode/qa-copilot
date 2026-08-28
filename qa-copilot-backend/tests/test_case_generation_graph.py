"""用例生成 Graph 中确定性校验规则的单元测试。"""

import json

from app.agents.case_generation_graph import (
    quality_and_duplicate_check,
    route_after_quality,
    route_after_validation,
    validate_generated_cases,
)
from app.agents.case_generation_schemas import CaseGenerationOutput


def _valid_case(local_id: str = "case-1", title: str = "发布文章成功") -> dict:
    """构造一条满足结构约束的最小生成用例。"""
    return {
        "local_id": local_id,
        "title": title,
        "case_type": "FUNCTIONAL",
        "priority": "P1",
        "preconditions": "用户已登录",
        "expected_summary": "文章发布成功",
        "automatable": True,
        "requirement_item_ids": [11],
        "generation_reason": "补齐正常发布流程",
        "source_case_ids": [21],
        "confidence": 0.9,
        "tags": ["文章"],
        "steps": [
            {
                "step_no": 1,
                "action": "填写合法文章并点击发布",
                "test_data": {"title": "测试文章"},
                "expected_result": "页面提示发布成功",
            }
        ],
    }


def test_validate_generated_cases_accepts_allowed_ids() -> None:
    """允许的需求点和参考用例 ID 应进入可信结构。"""
    result = validate_generated_cases(
        {
            "raw_output": json.dumps({"cases": [_valid_case()], "warnings": []}),
            "allowed_requirement_item_ids": [11],
            "allowed_source_case_ids": [21],
            "retry_count": 0,
        }
    )
    assert isinstance(result["generation_output"], CaseGenerationOutput)
    assert result["validation_errors"] == []


def test_validate_generated_cases_rejects_hallucinated_ids() -> None:
    """模型伪造的跨范围 ID 必须被白名单拦截并触发重试。"""
    result = validate_generated_cases(
        {
            "raw_output": json.dumps({"cases": [_valid_case()], "warnings": []}),
            "allowed_requirement_item_ids": [999],
            "allowed_source_case_ids": [],
            "retry_count": 0,
        }
    )
    assert result["generation_output"] is None
    assert result["retry_count"] == 1
    assert "未允许的需求点" in str(result["validation_feedback"])
    assert route_after_validation(result) == "retry"


def test_validate_generated_cases_rejects_uncovered_batch_requirement() -> None:
    """模型漏掉本批次任一需求点时必须重试，不能保存不完整批次。"""
    result = validate_generated_cases(
        {
            "raw_output": json.dumps(
                {"cases": [_valid_case()], "warnings": []}
            ),
            "allowed_requirement_item_ids": [11, 12],
            "allowed_source_case_ids": [21],
            "retry_count": 0,
        }
    )
    assert result["generation_output"] is None
    assert "没有生成测试用例：[12]" in str(
        result["validation_feedback"]
    )
    assert route_after_validation(result) == "retry"


def test_quality_check_rejects_duplicate_generated_cases() -> None:
    """同一批次语义高度重复的两条用例不能同时落库。"""
    output = CaseGenerationOutput.model_validate(
        {
            "cases": [
                _valid_case("case-1", "发布文章成功"),
                _valid_case("case-2", "发布文章成功"),
            ],
            "warnings": [],
        }
    )
    result = quality_and_duplicate_check(
        {
            "generation_output": output,
            "existing_case_signatures": [],
            "retry_count": 0,
        }
    )
    assert result["generation_output"] is None
    assert "本批次" in str(result["validation_feedback"])
    assert route_after_quality(result) == "retry"


def test_validation_stops_after_retry_limit() -> None:
    """有限重试耗尽后必须失败结束，避免无限调用模型。"""
    assert (
        route_after_validation(
            {"generation_output": None, "retry_count": 3}
        )
        == "failed"
    )
