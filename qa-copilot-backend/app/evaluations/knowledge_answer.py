"""知识问答端到端固定问题集指标计算。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from math import ceil
from statistics import median
from typing import Protocol


class CitationLike(Protocol):
    """回答评估实际需要的最小引用协议。"""

    chunk_id: int
    document_id: int


@dataclass(frozen=True, slots=True)
class AnswerEvaluationCase:
    """一条人工确认的问题、来源和答案事实。

    功能：定义问题应引用哪些来源，以及答案必须覆盖哪些事实组。
    作用：运行器使用它检查真实模型回答，不让模型自己决定评分标准。
    为什么用它：每个事实组可以提供多个同义表达，既保持确定性和可重复，
    又避免因为“第三方支付/三方支付”这类表述差异误判失败。
    """

    case_id: str
    question: str
    expected_document_ids: frozenset[int]
    expected_chunk_ids: frozenset[int]
    required_fact_groups: tuple[frozenset[str], ...]


@dataclass(frozen=True, slots=True)
class AnswerCaseResult:
    """一条真实回答的事实覆盖、引用质量、Token 和耗时明细。"""

    case_id: str
    question: str
    status: str
    answer: str
    required_fact_count: int
    matched_fact_count: int
    missing_fact_groups: list[list[str]]
    answer_key_point_coverage: float
    citation_count: int
    relevant_citation_count: int
    citation_accuracy: float
    citation_hit: bool
    cited_document_ids: list[int]
    cited_chunk_ids: list[int]
    latency_ms: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    error_message: str | None = None


def _normalize_text(value: str) -> str:
    """统一大小写、全半角和空白，降低格式差异对事实匹配的影响。"""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", "", normalized)


def evaluate_answer_case(
    case: AnswerEvaluationCase,
    *,
    answer: str,
    citations: list[CitationLike],
    latency_ms: float,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
) -> AnswerCaseResult:
    """检查一条答案的要点覆盖和引用来源是否正确。

    功能：使用人工确认的关键词组检查答案事实，并把引用映射到正确切片集合。
    作用：它是端到端评测中完全确定性的评分层，不依赖另一个模型打分。
    为什么用它：规则评分可重复、成本低且不会出现“生成模型给自己高分”；
    它不能识别所有语义和幻觉，因此无依据内容仍要进入独立人工复核。
    """

    normalized_answer = _normalize_text(answer)
    matched_fact_count = 0
    missing_fact_groups: list[list[str]] = []
    for fact_group in case.required_fact_groups:
        if any(_normalize_text(term) in normalized_answer for term in fact_group):
            matched_fact_count += 1
        else:
            missing_fact_groups.append(sorted(fact_group))

    required_fact_count = len(case.required_fact_groups)
    cited_chunk_ids = [citation.chunk_id for citation in citations]
    cited_document_ids = [citation.document_id for citation in citations]
    relevant_citation_count = sum(
        citation.chunk_id in case.expected_chunk_ids or citation.document_id in case.expected_document_ids
        for citation in citations
    )
    citation_count = len(citations)
    return AnswerCaseResult(
        case_id=case.case_id,
        question=case.question,
        status="SUCCESS",
        answer=answer,
        required_fact_count=required_fact_count,
        matched_fact_count=matched_fact_count,
        missing_fact_groups=missing_fact_groups,
        answer_key_point_coverage=(
            round(matched_fact_count / required_fact_count, 4) if required_fact_count else 0.0
        ),
        citation_count=citation_count,
        relevant_citation_count=relevant_citation_count,
        citation_accuracy=(round(relevant_citation_count / citation_count, 4) if citation_count else 0.0),
        citation_hit=relevant_citation_count > 0,
        cited_document_ids=cited_document_ids,
        cited_chunk_ids=cited_chunk_ids,
        latency_ms=round(latency_ms, 2),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def build_failed_answer_result(
    case: AnswerEvaluationCase,
    *,
    latency_ms: float,
    error_message: str,
) -> AnswerCaseResult:
    """把单题异常转换成可进入总体报告的失败明细。"""

    return AnswerCaseResult(
        case_id=case.case_id,
        question=case.question,
        status="FAILED",
        answer="",
        required_fact_count=len(case.required_fact_groups),
        matched_fact_count=0,
        missing_fact_groups=[sorted(group) for group in case.required_fact_groups],
        answer_key_point_coverage=0.0,
        citation_count=0,
        relevant_citation_count=0,
        citation_accuracy=0.0,
        citation_hit=False,
        cited_document_ids=[],
        cited_chunk_ids=[],
        latency_ms=round(latency_ms, 2),
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        error_message=error_message,
    )


def build_answer_evaluation_report(results: list[AnswerCaseResult]) -> dict[str, object]:
    """聚合端到端回答质量、引用、耗时和 Token 指标。

    功能：汇总成功率、平均要点覆盖率、引用准确率、引用命中率和延迟。
    作用：作为同一 Gold Label 数据集在模型、Prompt 或检索变更前后的基线。
    为什么用它：事实覆盖和引用分别统计，能区分“资料找对但回答漏要点”和
    “答案看似正确但引用错资料”两类问题。
    """

    total = len(results)
    successful_count = sum(result.status == "SUCCESS" for result in results)
    mean_key_point_coverage = (
        sum(result.answer_key_point_coverage for result in results) / total if total else 0.0
    )
    total_citations = sum(result.citation_count for result in results)
    total_relevant_citations = sum(result.relevant_citation_count for result in results)
    citation_accuracy = total_relevant_citations / total_citations if total_citations else 0.0
    citation_hit_rate = sum(result.citation_hit for result in results) / total if total else 0.0
    sorted_latencies = sorted(result.latency_ms for result in results)
    mean_latency_ms = sum(sorted_latencies) / total if total else 0.0
    median_latency_ms = median(sorted_latencies) if total else 0.0
    p95_latency_ms = sorted_latencies[max(ceil(total * 0.95) - 1, 0)] if total else 0.0
    max_latency_ms = sorted_latencies[-1] if total else 0.0

    return {
        "caseCount": total,
        "successfulCaseCount": successful_count,
        "successRate": round(successful_count / total, 4) if total else 0.0,
        "meanAnswerKeyPointCoverage": round(mean_key_point_coverage, 4),
        "citationAccuracy": round(citation_accuracy, 4),
        "citationHitRate": round(citation_hit_rate, 4),
        "meanLatencyMs": round(mean_latency_ms, 2),
        "medianLatencyMs": round(median_latency_ms, 2),
        "p95LatencyMs": round(p95_latency_ms, 2),
        "maxLatencyMs": round(max_latency_ms, 2),
        "totalInputTokens": sum(result.input_tokens for result in results),
        "totalOutputTokens": sum(result.output_tokens for result in results),
        "totalTokens": sum(result.total_tokens for result in results),
        "targetSuccessRate": 1.0,
        "targetMeanAnswerKeyPointCoverage": 0.85,
        "targetCitationAccuracy": 0.9,
        "targetCitationHitRate": 0.9,
        "passed": (
            total > 0
            and successful_count == total
            and mean_key_point_coverage >= 0.85
            and citation_accuracy >= 0.9
            and citation_hit_rate >= 0.9
        ),
        "unsupportedContentReviewStatus": "HUMAN_REVIEW_REQUIRED",
        "cases": [asdict(result) for result in results],
    }
