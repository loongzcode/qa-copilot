"""AI 生成测试用例的人工质量评估公式。"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import asdict, dataclass

ACCEPTED_STATUSES = frozenset({"APPROVED", "PUBLISHED", "DISABLED"})


@dataclass(frozen=True, slots=True)
class GeneratedCaseQualityFact:
    """一条 AI 生成用例参与质量评估所需的最小事实。

    功能：保存审核终态、需求关联、生成任务和步骤完整性等只读事实。
    作用：隔离数据库查询与指标公式，使评估公式可以用固定样本独立测试。
    为什么用它：直接在 SQL 中拼出最终百分比难以解释和单元测试；先读取事实再
    计算，可以在报告中追溯每一条用例为什么被计入某个指标。
    """

    case_id: int
    title: str
    status: str
    latest_human_action: str | None
    duplicate_marked: bool
    requirement_link_count: int
    invalid_requirement_link_count: int
    evidence_complete_link_count: int
    generation_task_traceable: bool
    step_count: int
    invalid_step_count: int


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    """计算比例，并在没有有效分母时返回 ``None``。

    功能：统一处理评估指标的除法和四位小数舍入。
    作用：避免“没有人工审核样本”被错误展示成 0% 或 100%。
    为什么用它：无样本表示指标不可判定，而不是质量为零；返回 ``None`` 能让
    报告和门禁明确区分“未达标”与“尚未评估”。
    """

    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _wilson_lower_bound(successes: int, total: int) -> float | None:
    """计算二项比例的 95% Wilson 置信区间下界。

    功能：估计在有限审核样本下，真实人工接受率可能达到的保守下界。
    作用：防止仅审核少量“看起来不错”的用例就宣称整个生成系统稳定有效。
    为什么用它：普通比例不体现样本量；Wilson 区间在小样本和 0%/100% 极端
    比例下比正态近似稳定。它只用于风险展示，正式门禁仍使用人工接受率与最小
    样本量两个可直观解释的条件。
    """

    if total == 0:
        return None
    z = 1.959963984540054
    observed = successes / total
    denominator = 1 + z**2 / total
    centre = observed + z**2 / (2 * total)
    margin = z * math.sqrt(
        observed * (1 - observed) / total + z**2 / (4 * total**2)
    )
    return round((centre - margin) / denominator, 4)


def _normalize_title(title: str) -> str:
    """规范化标题，用于发现大小写、空格或标点不同的机械重复用例。"""

    normalized = unicodedata.normalize("NFKC", title).casefold()
    return "".join(character for character in normalized if character.isalnum())


def build_case_generation_quality_report(
    facts: list[GeneratedCaseQualityFact],
    *,
    minimum_acceptance_rate: float = 0.7,
    maximum_duplicate_rate: float = 0.1,
    minimum_traceability_rate: float = 1.0,
    minimum_reviewed_cases: int = 20,
) -> dict[str, object]:
    """计算 AI 用例人工接受率、重复率和需求可追溯率。

    功能：把逐条用例事实汇总成可审计的质量指标和门禁结果。
    作用：为环境验收、持续集成报告和面试材料提供同一套可重复计算的口径。
    为什么用它：接受率必须只以已有人工决策的用例为分母；重复率以全部 AI
    候选用例为分母；可追溯率则要求每条候选用例都能关联回同项目需求点。三者
    分母不同，集中计算可以避免前端或临时 SQL 各自采用不同口径。
    """

    generated_count = len(facts)
    reviewed = [fact for fact in facts if fact.latest_human_action is not None]
    accepted = [fact for fact in reviewed if fact.status in ACCEPTED_STATUSES]
    duplicates = [fact for fact in facts if fact.duplicate_marked]
    normalized_title_counts: dict[str, int] = {}
    for fact in facts:
        normalized_title = _normalize_title(fact.title)
        normalized_title_counts[normalized_title] = (
            normalized_title_counts.get(normalized_title, 0) + 1
        )
    normalized_title_duplicate_count = sum(
        count - 1 for count in normalized_title_counts.values() if count > 1
    )
    traceable = [
        fact
        for fact in facts
        if fact.requirement_link_count > 0
        and fact.invalid_requirement_link_count == 0
    ]
    evidence_complete = [
        fact
        for fact in facts
        if fact.requirement_link_count > 0
        and fact.evidence_complete_link_count == fact.requirement_link_count
    ]
    task_traceable = [fact for fact in facts if fact.generation_task_traceable]
    executable_steps = [
        fact
        for fact in facts
        if fact.step_count > 0 and fact.invalid_step_count == 0
    ]

    acceptance_rate = _safe_ratio(len(accepted), len(reviewed))
    manual_duplicate_rate = _safe_ratio(len(duplicates), generated_count)
    normalized_title_duplicate_rate = _safe_ratio(
        normalized_title_duplicate_count, generated_count
    )
    duplicate_rate_candidates = [
        value
        for value in (manual_duplicate_rate, normalized_title_duplicate_rate)
        if value is not None
    ]
    duplicate_rate = max(duplicate_rate_candidates, default=None)
    traceability_rate = _safe_ratio(len(traceable), generated_count)
    evidence_completeness_rate = _safe_ratio(len(evidence_complete), generated_count)
    task_traceability_rate = _safe_ratio(len(task_traceable), generated_count)
    executable_step_rate = _safe_ratio(len(executable_steps), generated_count)

    gates = {
        "has_generated_cases": generated_count > 0,
        "has_human_reviews": len(reviewed) > 0,
        "minimum_review_sample_passed": len(reviewed) >= minimum_reviewed_cases,
        "acceptance_rate_passed": (
            acceptance_rate is not None
            and acceptance_rate >= minimum_acceptance_rate
        ),
        "duplicate_rate_passed": (
            duplicate_rate is not None
            and duplicate_rate < maximum_duplicate_rate
        ),
        "traceability_rate_passed": (
            traceability_rate is not None
            and traceability_rate >= minimum_traceability_rate
        ),
    }

    return {
        "generatedCaseCount": generated_count,
        "reviewedCaseCount": len(reviewed),
        "acceptedCaseCount": len(accepted),
        "duplicateCaseCount": len(duplicates),
        "traceableCaseCount": len(traceable),
        "acceptanceRate": acceptance_rate,
        "acceptanceRateWilsonLowerBound95": _wilson_lower_bound(
            len(accepted), len(reviewed)
        ),
        "manualDuplicateRate": manual_duplicate_rate,
        "normalizedTitleDuplicateRate": normalized_title_duplicate_rate,
        "duplicateRate": duplicate_rate,
        "requirementTraceabilityRate": traceability_rate,
        "evidenceCompletenessRate": evidence_completeness_rate,
        "generationTaskTraceabilityRate": task_traceability_rate,
        "executableStepRate": executable_step_rate,
        "targets": {
            "minimumAcceptanceRate": minimum_acceptance_rate,
            "minimumReviewedCases": minimum_reviewed_cases,
            "maximumDuplicateRateExclusive": maximum_duplicate_rate,
            "minimumRequirementTraceabilityRate": minimum_traceability_rate,
        },
        "gates": gates,
        "passed": all(gates.values()),
        "cases": [asdict(fact) for fact in facts],
    }
