"""历史标准用例检索、覆盖判断和覆盖矩阵构建服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from app.agents.case_generation_schemas import CoverageAnalysisOutput
from app.core.constants import AIModelTaskType, RequirementCoverageType
from app.exceptions import BadRequestException, ExternalServiceException, InternalServerException
from app.mappers.requirements import requirement_item_to_vo
from app.models import AIModel, PromptTemplate, Requirement, RequirementCaseLink, TestCase
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.repositories.test_cases_repository import TestCasesRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.schemas.vo.test_cases import CoverageLinkVO, CoverageMatrixVO, CoverageRowVO
from app.utils.ai_client_util import generate_text_with_langchain


@dataclass(slots=True)
class CoverageAnalysisResult:
    """覆盖分析结果及可审计的历史用例召回快照。"""

    matrix: CoverageMatrixVO
    retrieval_snapshot: dict[str, object]


class CaseCoverageService:
    """检索标准用例并建立需求点到用例的覆盖关系。

    功能：先用确定性的数据库检索缩小候选范围，再让模型判断 FULL/PARTIAL，最后
    将结论落库并构建覆盖矩阵。
    作用：连接“已确认需求点”和“只为覆盖缺口生成用例”两个阶段；生成流程必须
    使用这里的结论，不能跳过历史资产复用直接生成全部用例。
    为什么用它：检索负责召回、模型负责语义判断、Pydantic 和 ID 白名单负责约束，
    三层分工比只依赖关键词或只依赖大模型更可控、成本更低且能够审计。
    """

    def __init__(
        self,
        repository: TestCasesRepository,
        ai_model_repository: AIModelRepository,
        prompt_template_repository: PromptTemplateRepository,
    ) -> None:
        self.repository = repository
        self.ai_model_repository = ai_model_repository
        self.prompt_template_repository = prompt_template_repository

    async def _load_ai_configuration(self) -> tuple[AIModel, PromptTemplate]:
        """读取并校验覆盖分析使用的默认模型与 Prompt。

        功能：检查模型、服务商、任务能力和 ``coverage_analysis`` 模板。
        作用：在检索完成、模型调用开始前快速暴露配置错误。
        为什么用它：集中前置校验能返回明确业务错误，避免配置问题被包装成难懂的
        SDK 异常；配置来自数据库，管理员可切换模型而无需改代码。
        """
        model = await self.ai_model_repository.get_default_model()
        if model is None or not model.enabled:
            raise InternalServerException("未配置已启用的默认覆盖分析模型")
        if not model.provider.enabled:
            raise InternalServerException("默认覆盖分析模型的服务商已停用")
        if AIModelTaskType.COVERAGE_ANALYSIS.value not in model.task_types:
            raise InternalServerException("默认模型不支持覆盖分析")
        prompt = await self.prompt_template_repository.get_by_code("coverage_analysis")
        if prompt is None or not prompt.enabled:
            raise InternalServerException("未配置已启用的 coverage_analysis Prompt")
        return model, prompt

    @staticmethod
    def _case_to_prompt(case: TestCase, score: float) -> dict[str, object]:
        """将 ORM 用例压缩为覆盖模型真正需要的字段，控制 Prompt 体积。"""
        return {
            "id": case.id,
            "case_code": case.case_code,
            "title": case.title,
            "module_id": case.module_id,
            "module_name": case.module.name if case.module else None,
            "case_type": case.case_type,
            "priority": case.priority,
            "preconditions": case.preconditions,
            "expected_summary": case.expected_summary,
            "retrieval_score": round(score, 4),
            "steps": [
                {
                    "step_no": step.step_no,
                    "action": step.action,
                    "expected_result": step.expected_result,
                }
                for step in sorted(case.steps, key=lambda item: item.step_no)
            ],
        }

    async def get_matrix(
        self,
        project_id: int,
        requirement_id: int,
    ) -> CoverageMatrixVO:
        """根据数据库现有覆盖关系构建矩阵，不重新调用模型。

        功能：汇总已确认需求点的 FULL、PARTIAL 和 UNCOVERED 状态。
        作用：支撑 GET 覆盖矩阵、任务执行前缺口计算和任务完成后的页面刷新。
        为什么用它：矩阵是数据库事实的投影，查询不应产生副作用或重复模型费用。
        """
        items = await self.repository.list_confirmed_requirement_items(
            project_id,
            requirement_id,
        )
        links = await self.repository.list_requirement_links(requirement_id)
        links_by_item: dict[int, list[RequirementCaseLink]] = {}
        for link in links:
            links_by_item.setdefault(link.requirement_item_id, []).append(link)

        rows: list[CoverageRowVO] = []
        full_count = 0
        partial_count = 0
        uncovered_count = 0
        for item in items:
            item_links = links_by_item.get(item.id, [])
            if any(link.coverage_type == RequirementCoverageType.FULL.value for link in item_links):
                coverage_status = RequirementCoverageType.FULL.value
                full_count += 1
            elif item_links:
                coverage_status = RequirementCoverageType.PARTIAL.value
                partial_count += 1
            else:
                coverage_status = "UNCOVERED"
                uncovered_count += 1
            rows.append(
                CoverageRowVO(
                    requirement_item=requirement_item_to_vo(item),
                    coverage_status=coverage_status,
                    links=[
                        CoverageLinkVO(
                            requirement_item_id=link.requirement_item_id,
                            test_case_id=link.test_case_id,
                            test_case_code=link.test_case.case_code,
                            test_case_title=link.test_case.title,
                            coverage_type=link.coverage_type,
                            confidence=link.confidence,
                            evidence=link.evidence,
                        )
                        for link in item_links
                    ],
                )
            )
        return CoverageMatrixVO(
            requirement_id=requirement_id,
            total_items=len(items),
            full_count=full_count,
            partial_count=partial_count,
            uncovered_count=uncovered_count,
            rows=rows,
        )

    async def analyze(
        self,
        requirement: Requirement,
        *,
        user_id: int | None,
        task_id: str | None = None,
    ) -> CoverageAnalysisResult:
        """检索历史标准用例并用模型重建 AI 覆盖关系。

        功能：逐需求点召回候选，批量调用模型判断覆盖程度，校验模型引用的 ID，
        保留人工关系并替换旧 AI 结论。
        作用：为覆盖分析页面提供结论，也为缺失用例生成任务确定真正的缺口。
        为什么用它：批量判断比每个候选单独调用模型更省费用；先在内存完成全部校验、
        再在一个事务中替换数据库关系，避免半批成功导致矩阵不一致。
        """
        items = await self.repository.list_confirmed_requirement_items(
            requirement.project_id,
            requirement.id,
        )
        if not items:
            raise BadRequestException("请先确认至少一个原子需求点")

        candidates_by_item: dict[int, list[tuple[TestCase, float]]] = {}
        unique_cases: dict[int, tuple[TestCase, float]] = {}
        for item in items:
            query_text = " ".join(
                part
                for part in [
                    item.title,
                    item.description,
                    item.acceptance_criteria,
                ]
                if part
            )
            candidates = await self.repository.search_published_cases(
                requirement.project_id,
                query_text,
                requirement.module_id,
                limit=10,
            )
            # 过滤完全无相似度且不同模块的结果，防止把无关用例交给模型硬判。
            candidates = [
                candidate
                for candidate in candidates
                if candidate[1] > 0.05
                or (
                    requirement.module_id is not None
                    and candidate[0].module_id == requirement.module_id
                )
            ]
            candidates_by_item[item.id] = candidates
            for candidate_case, score in candidates:
                previous = unique_cases.get(candidate_case.id)
                if previous is None or score > previous[1]:
                    unique_cases[candidate_case.id] = (candidate_case, score)

        retrieval_snapshot: dict[str, object] = {
            "strategy": "pg_trgm_with_module_boost",
            "items": {
                str(item_id): [
                    {"test_case_id": test_case.id, "score": round(score, 4)}
                    for test_case, score in candidates
                ]
                for item_id, candidates in candidates_by_item.items()
            },
        }
        if not unique_cases:
            await self.repository.delete_ai_coverage_links(requirement.id)
            await self.repository.commit()
            return CoverageAnalysisResult(
                matrix=await self.get_matrix(requirement.project_id, requirement.id),
                retrieval_snapshot=retrieval_snapshot,
            )

        model, prompt = await self._load_ai_configuration()
        chat_prompt = ChatPromptTemplate.from_messages(
            [("system", prompt.system_prompt), ("human", prompt.user_prompt)]
        )
        allowed_pairs = {
            (item_id, test_case.id)
            for item_id, candidates in candidates_by_item.items()
            for test_case, _ in candidates
        }
        requirements_payload = [
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "item_type": item.item_type,
                "priority": item.priority,
                "acceptance_criteria": item.acceptance_criteria,
            }
            for item in items
        ]
        candidate_payload = [
            self._case_to_prompt(test_case, score)
            for test_case, score in unique_cases.values()
        ]
        validation_feedback = ""
        parsed_output: CoverageAnalysisOutput | None = None
        last_error = ""
        for _ in range(2):
            generation = await generate_text_with_langchain(
                repository=self.ai_model_repository,
                provider=model.provider,
                model=model,
                chat_prompt=chat_prompt,
                input_variables={
                    "requirements_json": json.dumps(requirements_payload, ensure_ascii=False),
                    "candidate_cases_json": json.dumps(candidate_payload, ensure_ascii=False),
                    "output_schema": json.dumps(
                        CoverageAnalysisOutput.model_json_schema(),
                        ensure_ascii=False,
                    ),
                    "validation_feedback": validation_feedback,
                },
                task_type=AIModelTaskType.COVERAGE_ANALYSIS.value,
                usage_context=AIUsageContextDTO(
                    user_id=user_id,
                    project_id=requirement.project_id,
                    task_id=task_id,
                    retrieval_hit_count=len(unique_cases),
                ),
            )
            try:
                candidate_output = CoverageAnalysisOutput.model_validate_json(
                    generation.content
                )
                invalid_pairs = [
                    (decision.requirement_item_id, decision.test_case_id)
                    for decision in candidate_output.decisions
                    if (decision.requirement_item_id, decision.test_case_id)
                    not in allowed_pairs
                ]
                if invalid_pairs:
                    raise ValueError(f"模型引用了未提供的需求点/用例组合：{invalid_pairs[:10]}")
                parsed_output = candidate_output
                break
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)
                validation_feedback = f"上次输出校验失败，请仅修复 JSON：{last_error[:3000]}"

        if parsed_output is None:
            raise ExternalServiceException(f"覆盖分析结构化输出校验失败：{last_error}")

        existing_links = await self.repository.list_requirement_links(requirement.id)
        manual_pairs = {
            (link.requirement_item_id, link.test_case_id)
            for link in existing_links
            if link.evidence.get("source") != "AI_ANALYSIS"
        }
        await self.repository.delete_ai_coverage_links(requirement.id)
        for decision in parsed_output.decisions:
            pair = (decision.requirement_item_id, decision.test_case_id)
            if pair in manual_pairs:
                continue
            self.repository.add(
                RequirementCaseLink(
                    requirement_item_id=decision.requirement_item_id,
                    test_case_id=decision.test_case_id,
                    coverage_type=decision.coverage_type.value,
                    confidence=decision.confidence,
                    evidence={
                        "source": "AI_ANALYSIS",
                        "reason": decision.reason,
                        "covered_aspects": decision.covered_aspects,
                        "missing_aspects": decision.missing_aspects,
                        "model_id": model.id,
                        "prompt_template_id": prompt.id,
                    },
                    created_by=user_id,
                )
            )
        await self.repository.commit()
        return CoverageAnalysisResult(
            matrix=await self.get_matrix(requirement.project_id, requirement.id),
            retrieval_snapshot=retrieval_snapshot,
        )
