from dataclasses import dataclass

from app.evaluations.knowledge_retrieval import (
    RetrievalEvaluationCase,
    build_evaluation_report,
    evaluate_retrieval_case,
)


@dataclass
class Result:
    chunk_id: int
    document_id: int


def test_evaluation_accepts_document_or_exact_chunk_evidence() -> None:
    case = RetrievalEvaluationCase(
        case_id="case-1",
        question="如何发布？",
        expected_document_ids=frozenset({10}),
        expected_chunk_ids=frozenset({99}),
    )
    result = evaluate_retrieval_case(
        case,
        [Result(chunk_id=1, document_id=10), Result(chunk_id=99, document_id=20), Result(chunk_id=2, document_id=30)],
    )
    assert result.hit_at_10 is True
    assert result.relevant_count == 2
    assert result.precision_at_10 == 0.6667
    assert result.recall_at_10 == 1.0
    assert result.first_relevant_rank == 1
    assert result.reciprocal_rank == 1.0


def test_report_uses_project_hit_at_10_threshold() -> None:
    cases = []
    for index in range(20):
        expected = index < 17
        cases.append(
            evaluate_retrieval_case(
                RetrievalEvaluationCase(
                    case_id=str(index),
                    question="q",
                    expected_document_ids=frozenset({1}),
                    expected_chunk_ids=frozenset(),
                ),
                [Result(chunk_id=index, document_id=1 if expected else 2)],
            )
        )
    report = build_evaluation_report(cases)
    assert report["hitAt10"] == 0.85
    assert report["meanRecallAt10"] == 0.85
    assert report["meanReciprocalRank"] == 0.85
    assert report["passed"] is True
