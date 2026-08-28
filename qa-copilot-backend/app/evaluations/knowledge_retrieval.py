"""知识检索固定问题集指标计算。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil
from statistics import median
from typing import Protocol


class RetrievalResultLike(Protocol):
    """评测器实际需要的最小检索结果协议。"""

    chunk_id: int
    document_id: int


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationCase:
    """一条人工标注的固定问题及其正确来源集合。"""

    case_id: str
    question: str
    expected_document_ids: frozenset[int]
    expected_chunk_ids: frozenset[int]


@dataclass(frozen=True, slots=True)
class RetrievalCaseResult:
    """单个问题的检索结果，便于定位召回和排序问题。

    功能：保存一条固定问题的命中、召回、首个正确结果排名和耗时。
    作用：评测报告会聚合这些明细，同时保留失败题用于人工排查。
    为什么用它：检索质量和回答引用质量属于两个不同阶段；这里不再把
    Top 5 检索精确率错误地命名成“引用准确率”。
    """

    case_id: str
    question: str
    hit_at_10: bool
    relevant_count: int
    returned_count: int
    precision_at_10: float
    recall_at_10: float
    first_relevant_rank: int | None
    reciprocal_rank: float
    latency_ms: float
    retrieved_document_ids: list[int]
    retrieved_chunk_ids: list[int]


def evaluate_retrieval_case(
    case: RetrievalEvaluationCase,
    results: list[RetrievalResultLike],
    *,
    latency_ms: float = 0.0,
) -> RetrievalCaseResult:
    """计算一个问题的 Top 10 命中、召回率和倒数排名。

    功能：判断返回结果是否命中人工标注的文档或切片，并统计相关证据覆盖率。
    作用：由批量评测脚本逐题调用；明细用于排查是召回、排序还是标注出了问题。
    为什么用它：Hit@10 只能说明“至少找到一个”，Recall@10 判断正确证据是否找全，
    Reciprocal Rank（倒数排名）还能反映正确证据是否排在靠前位置。
    """
    top_results = results[:10]
    relevant_flags = [
        result.chunk_id in case.expected_chunk_ids or result.document_id in case.expected_document_ids
        for result in top_results
    ]
    relevant_count = sum(relevant_flags)
    returned_count = len(top_results)

    matched_chunk_ids = {
        result.chunk_id for result in top_results if result.chunk_id in case.expected_chunk_ids
    }
    matched_document_ids = {
        result.document_id for result in top_results if result.document_id in case.expected_document_ids
    }
    expected_evidence_count = len(case.expected_chunk_ids) + len(case.expected_document_ids)
    matched_evidence_count = len(matched_chunk_ids) + len(matched_document_ids)

    first_relevant_rank = next(
        (rank for rank, is_relevant in enumerate(relevant_flags, start=1) if is_relevant),
        None,
    )
    return RetrievalCaseResult(
        case_id=case.case_id,
        question=case.question,
        hit_at_10=relevant_count > 0,
        relevant_count=relevant_count,
        returned_count=returned_count,
        precision_at_10=round(relevant_count / returned_count, 4) if returned_count else 0.0,
        recall_at_10=(round(matched_evidence_count / expected_evidence_count, 4) if expected_evidence_count else 0.0),
        first_relevant_rank=first_relevant_rank,
        reciprocal_rank=(round(1 / first_relevant_rank, 4) if first_relevant_rank is not None else 0.0),
        latency_ms=round(latency_ms, 2),
        retrieved_document_ids=[item.document_id for item in top_results],
        retrieved_chunk_ids=[item.chunk_id for item in top_results],
    )


def build_evaluation_report(results: list[RetrievalCaseResult]) -> dict[str, object]:
    """聚合固定问题集的检索质量和耗时，并判断是否通过基线阈值。

    功能：计算 Hit@10、平均 Recall@10、Mean Reciprocal Rank（平均倒数排名，MRR）
    和 P95 延迟。
    作用：作为同一冻结问题集在不同模型、索引或 Rerank 配置间的比较基线。
    为什么用它：这些指标只依赖固定问题和人工来源标注，结果可重复；回答正文和
    引用准确率必须由端到端回答评测另行计算，不能由检索候选冒充。
    """
    total = len(results)
    hit_rate = sum(item.hit_at_10 for item in results) / total if total else 0.0
    mean_precision = sum(item.precision_at_10 for item in results) / total if total else 0.0
    mean_recall = sum(item.recall_at_10 for item in results) / total if total else 0.0
    mean_reciprocal_rank = sum(item.reciprocal_rank for item in results) / total if total else 0.0
    sorted_latencies = sorted(item.latency_ms for item in results)
    mean_latency_ms = sum(sorted_latencies) / total if total else 0.0
    median_latency_ms = median(sorted_latencies) if total else 0.0
    p95_latency_ms = sorted_latencies[max(ceil(total * 0.95) - 1, 0)] if total else 0.0
    max_latency_ms = sorted_latencies[-1] if total else 0.0
    return {
        "caseCount": total,
        "hitAt10": round(hit_rate, 4),
        "meanRecallAt10": round(mean_recall, 4),
        "meanPrecisionAt10": round(mean_precision, 4),
        "meanReciprocalRank": round(mean_reciprocal_rank, 4),
        "meanLatencyMs": round(mean_latency_ms, 2),
        "medianLatencyMs": round(median_latency_ms, 2),
        "p95LatencyMs": round(p95_latency_ms, 2),
        "maxLatencyMs": round(max_latency_ms, 2),
        "targetHitAt10": 0.85,
        "targetMeanRecallAt10": 0.85,
        "targetMeanReciprocalRank": 0.7,
        "passed": (
            total > 0
            and hit_rate >= 0.85
            and mean_recall >= 0.85
            and mean_reciprocal_rank >= 0.7
        ),
        "cases": [asdict(item) for item in results],
    }
