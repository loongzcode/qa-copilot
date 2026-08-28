from scripts.build_knowledge_answer_evidence import build_evidence


def _result(
    case_id: str,
    *,
    matched: int,
    required: int,
    relevant_citations: int,
    citations: int,
    latency_ms: float,
) -> dict[str, object]:
    """构造最小评测结果，便于验证聚合公式而不调用模型。"""

    return {
        "case_id": case_id,
        "status": "SUCCESS",
        "required_fact_count": required,
        "matched_fact_count": matched,
        "citation_count": citations,
        "relevant_citation_count": relevant_citations,
        "citation_hit": relevant_citations > 0,
        "latency_ms": latency_ms,
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }


def test_build_evidence_separates_human_and_synthetic_metrics() -> None:
    """人工 Gold 和合成回归题必须分层统计，不能用合成样本冒充人工指标。"""

    dataset = {
        "datasetId": "demo",
        "version": "v1",
        "goldLabelStatus": "MIXED_REVIEW_REQUIRED",
        "cases": [
            {
                "id": "human-1",
                "question": "人工题",
                "expectedChunkIds": [1],
            },
            {
                "id": "synthetic-1",
                "question": "合成题",
                "provenance": "SYNTHETIC_GROUNDED",
                "category": "FACT",
                "expectedChunkIds": [2],
            },
        ],
    }
    report = {
        "cases": [
            _result(
                "human-1",
                matched=2,
                required=2,
                relevant_citations=1,
                citations=1,
                latency_ms=100,
            ),
            _result(
                "synthetic-1",
                matched=1,
                required=2,
                relevant_citations=1,
                citations=2,
                latency_ms=200,
            ),
        ]
    }

    evidence = build_evidence(dataset, report)

    assert evidence["dataset"]["humanConfirmedCaseCount"] == 1
    assert evidence["dataset"]["syntheticGroundedCaseCount"] == 1
    assert evidence["metrics"]["humanGold"]["keyPointCoverage"] == 1.0
    assert evidence["metrics"]["syntheticGrounded"]["keyPointCoverage"] == 0.5
    assert evidence["metrics"]["allMixedRegression"]["keyPointCoverage"] == 0.75
    assert evidence["metrics"]["allMixedRegression"]["citationAccuracy"] == 0.6667
