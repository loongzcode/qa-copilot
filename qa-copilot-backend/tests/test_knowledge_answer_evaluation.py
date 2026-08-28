from dataclasses import dataclass

from app.evaluations.knowledge_answer import (
    AnswerEvaluationCase,
    build_answer_evaluation_report,
    evaluate_answer_case,
)


@dataclass
class Citation:
    chunk_id: int
    document_id: int


def test_answer_evaluation_scores_fact_groups_and_citations() -> None:
    case = AnswerEvaluationCase(
        case_id="case-1",
        question="什么是支付网关？",
        expected_document_ids=frozenset(),
        expected_chunk_ids=frozenset({143}),
        required_fact_groups=(
            frozenset({"pay系统", "pay"}),
            frozenset({"第三方支付", "三方支付"}),
        ),
    )
    result = evaluate_answer_case(
        case,
        answer="支付网关指 PAY 系统，负责对接第三方支付渠道。[资料1]",
        citations=[Citation(chunk_id=143, document_id=46)],
        latency_ms=123.456,
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
    )
    assert result.answer_key_point_coverage == 1.0
    assert result.citation_accuracy == 1.0
    assert result.citation_hit is True
    assert result.latency_ms == 123.46


def test_answer_report_fails_when_one_case_cites_wrong_source() -> None:
    case = AnswerEvaluationCase(
        case_id="case-1",
        question="q",
        expected_document_ids=frozenset(),
        expected_chunk_ids=frozenset({1}),
        required_fact_groups=(frozenset({"正确事实"}),),
    )
    results = [
        evaluate_answer_case(
            case,
            answer="正确事实",
            citations=[Citation(chunk_id=2, document_id=2)],
            latency_ms=10,
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
        )
    ]
    report = build_answer_evaluation_report(results)
    assert report["meanAnswerKeyPointCoverage"] == 1.0
    assert report["citationAccuracy"] == 0.0
    assert report["passed"] is False
