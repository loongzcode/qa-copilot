"""需求拆解、用例生成和自动化准备之间的确定性多 Agent 协调规则。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class QualityDeliveryStage(StrEnum):
    """质量交付流程当前阶段；名称会直接返回给前端和审计日志。"""

    START_REQUIREMENT_AGENT = "START_REQUIREMENT_AGENT"
    REQUIREMENT_AGENT_RUNNING = "REQUIREMENT_AGENT_RUNNING"
    REQUIREMENT_AGENT_FAILED = "REQUIREMENT_AGENT_FAILED"
    HUMAN_REQUIREMENT_REVIEW = "HUMAN_REQUIREMENT_REVIEW"
    START_CASE_AGENT = "START_CASE_AGENT"
    CASE_AGENT_RUNNING = "CASE_AGENT_RUNNING"
    CASE_AGENT_FAILED = "CASE_AGENT_FAILED"
    HUMAN_CASE_REVIEW = "HUMAN_CASE_REVIEW"
    IMPROVE_AUTOMATION_DATA = "IMPROVE_AUTOMATION_DATA"
    READY_FOR_AUTOMATION = "READY_FOR_AUTOMATION"


@dataclass(frozen=True, slots=True)
class QualityDeliveryFacts:
    """协调器作决定所需的最小事实，不把数据库对象传入 Agent 状态机。"""

    requirement_item_count: int
    confirmed_item_count: int
    extraction_status: str | None
    generation_status: str | None
    review_case_count: int
    published_case_count: int
    automatable_published_case_count: int


@dataclass(frozen=True, slots=True)
class QualityDeliveryDecision:
    """协调结果：当前由谁处理、下一步动作以及阻塞原因。"""

    stage: QualityDeliveryStage
    current_agent: str | None
    next_action: str
    blockers: tuple[str, ...] = ()


def coordinate_quality_delivery(facts: QualityDeliveryFacts) -> QualityDeliveryDecision:
    """根据持久化事实选择下一位 Agent 或人工关卡。

    功能：把需求 Agent、用例 Agent、自动化准备 Agent 串成有限状态流程。
    作用：API、定时任务或未来 LangGraph 外层编排都复用同一组跳转规则。
    为什么用它：跨 Agent 的安全边界应由确定性代码控制，模型不能自行跳过需求点
    确认和用例发布；纯函数也比把判断散落在多个 Service 中更容易单元测试。
    """
    if facts.requirement_item_count == 0:
        if facts.extraction_status in {"PENDING", "RUNNING"}:
            return QualityDeliveryDecision(
                QualityDeliveryStage.REQUIREMENT_AGENT_RUNNING,
                "RequirementAnalysisAgent",
                "等待需求拆解任务完成",
            )
        if facts.extraction_status == "FAILED":
            return QualityDeliveryDecision(
                QualityDeliveryStage.REQUIREMENT_AGENT_FAILED,
                "RequirementAnalysisAgent",
                "检查失败原因并重新提交需求拆解",
                ("最近一次需求拆解失败",),
            )
        return QualityDeliveryDecision(
            QualityDeliveryStage.START_REQUIREMENT_AGENT,
            "RequirementAnalysisAgent",
            "提交需求拆解任务",
        )

    if facts.confirmed_item_count < facts.requirement_item_count:
        return QualityDeliveryDecision(
            QualityDeliveryStage.HUMAN_REQUIREMENT_REVIEW,
            None,
            "人工校正并确认全部需求点",
            (f"尚有 {facts.requirement_item_count - facts.confirmed_item_count} 条需求点未确认",),
        )

    if facts.generation_status in {"PENDING", "RUNNING"}:
        return QualityDeliveryDecision(
            QualityDeliveryStage.CASE_AGENT_RUNNING,
            "TestCaseGenerationAgent",
            "等待覆盖分析和缺失用例生成完成",
        )
    if facts.generation_status == "FAILED":
        return QualityDeliveryDecision(
            QualityDeliveryStage.CASE_AGENT_FAILED,
            "TestCaseGenerationAgent",
            "检查失败原因并重新执行覆盖分析和缺失用例生成",
            ("最近一次测试用例生成失败",),
        )
    if facts.generation_status == "WAITING_REVIEW" or facts.review_case_count > 0:
        return QualityDeliveryDecision(
            QualityDeliveryStage.HUMAN_CASE_REVIEW,
            None,
            "人工接受、修改或驳回 AI 草稿，并发布合格用例",
            (f"有 {facts.review_case_count} 条用例等待人工处理",),
        )
    if facts.published_case_count == 0:
        return QualityDeliveryDecision(
            QualityDeliveryStage.START_CASE_AGENT,
            "TestCaseGenerationAgent",
            "启动覆盖分析并生成缺失用例",
        )
    if facts.automatable_published_case_count == 0:
        return QualityDeliveryDecision(
            QualityDeliveryStage.IMPROVE_AUTOMATION_DATA,
            "AutomationReadinessAgent",
            "为已发布 API 用例补齐结构化请求、断言和可自动化标记",
            ("尚无达到自动化就绪标准的已发布用例",),
        )
    return QualityDeliveryDecision(
        QualityDeliveryStage.READY_FOR_AUTOMATION,
        "AutomationReadinessAgent",
        "转换为受控自动化定义并进入审批",
    )
