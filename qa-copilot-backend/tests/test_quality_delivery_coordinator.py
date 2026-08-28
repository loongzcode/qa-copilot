"""多 Agent 协调状态机的人工作业边界测试。"""

from app.agents.quality_delivery_coordinator import (
    QualityDeliveryFacts,
    QualityDeliveryStage,
    coordinate_quality_delivery,
)


def facts(**changes) -> QualityDeliveryFacts:
    """构造默认流程事实，让每个测试只突出发生变化的字段。"""
    values = {
        "requirement_item_count": 0,
        "confirmed_item_count": 0,
        "extraction_status": None,
        "generation_status": None,
        "review_case_count": 0,
        "published_case_count": 0,
        "automatable_published_case_count": 0,
    }
    values.update(changes)
    return QualityDeliveryFacts(**values)


def test_coordinator_never_skips_requirement_human_review() -> None:
    decision = coordinate_quality_delivery(facts(requirement_item_count=4, confirmed_item_count=3))
    assert decision.stage == QualityDeliveryStage.HUMAN_REQUIREMENT_REVIEW
    assert decision.current_agent is None


def test_coordinator_routes_confirmed_requirement_to_case_agent() -> None:
    decision = coordinate_quality_delivery(facts(requirement_item_count=4, confirmed_item_count=4))
    assert decision.stage == QualityDeliveryStage.START_CASE_AGENT
    assert decision.current_agent == "TestCaseGenerationAgent"


def test_coordinator_never_auto_publishes_generated_cases() -> None:
    decision = coordinate_quality_delivery(
        facts(
            requirement_item_count=4,
            confirmed_item_count=4,
            generation_status="WAITING_REVIEW",
            review_case_count=6,
        )
    )
    assert decision.stage == QualityDeliveryStage.HUMAN_CASE_REVIEW
    assert decision.current_agent is None


def test_coordinator_routes_approved_automatable_cases_to_automation() -> None:
    decision = coordinate_quality_delivery(
        facts(
            requirement_item_count=4,
            confirmed_item_count=4,
            published_case_count=3,
            automatable_published_case_count=2,
        )
    )
    assert decision.stage == QualityDeliveryStage.READY_FOR_AUTOMATION


def test_failed_case_generation_is_reported_instead_of_silently_restarting() -> None:
    """生成失败应先暴露失败原因，不能让页面误以为尚未开始。"""
    decision = coordinate_quality_delivery(
        facts(
            requirement_item_count=2,
            confirmed_item_count=2,
            generation_status="FAILED",
        )
    )

    assert decision.stage == QualityDeliveryStage.CASE_AGENT_FAILED
    assert decision.blockers == ("最近一次测试用例生成失败",)
