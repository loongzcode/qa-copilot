from dataclasses import replace

from app.evaluations.case_generation_quality import (
    GeneratedCaseQualityFact,
    build_case_generation_quality_report,
)


def _fact(
    case_id: int,
    *,
    status: str = "PUBLISHED",
    action: str | None = "PUBLISH",
    duplicate: bool = False,
    links: int = 1,
) -> GeneratedCaseQualityFact:
    return GeneratedCaseQualityFact(
        case_id=case_id,
        title=f"用例 {case_id}",
        status=status,
        latest_human_action=action,
        duplicate_marked=duplicate,
        requirement_link_count=links,
        invalid_requirement_link_count=0,
        evidence_complete_link_count=links,
        generation_task_traceable=True,
        step_count=1,
        invalid_step_count=0,
    )


def test_report_uses_reviewed_cases_as_acceptance_denominator() -> None:
    report = build_case_generation_quality_report(
        [
            _fact(1),
            _fact(2, status="REJECTED", action="REJECT"),
            _fact(3, status="DRAFT", action=None),
        ]
    )

    assert report["reviewedCaseCount"] == 2
    assert report["acceptedCaseCount"] == 1
    assert report["acceptanceRate"] == 0.5
    assert report["gates"]["acceptance_rate_passed"] is False
    assert report["gates"]["minimum_review_sample_passed"] is False


def test_report_requires_every_generated_case_to_be_traceable() -> None:
    report = build_case_generation_quality_report([_fact(1), _fact(2, links=0)])

    assert report["requirementTraceabilityRate"] == 0.5
    assert report["gates"]["traceability_rate_passed"] is False


def test_report_applies_strict_duplicate_threshold() -> None:
    facts = [_fact(index) for index in range(1, 11)]
    facts[-1] = _fact(10, status="REJECTED", action="DUPLICATE", duplicate=True)

    report = build_case_generation_quality_report(facts)

    assert report["duplicateRate"] == 0.1
    assert report["gates"]["duplicate_rate_passed"] is False


def test_report_detects_normalized_title_duplicates() -> None:
    first = _fact(1)
    second = replace(first, case_id=2, title="用例-1！")

    report = build_case_generation_quality_report(
        [first, second], minimum_reviewed_cases=2
    )

    assert report["normalizedTitleDuplicateRate"] == 0.5
    assert report["duplicateRate"] == 0.5
