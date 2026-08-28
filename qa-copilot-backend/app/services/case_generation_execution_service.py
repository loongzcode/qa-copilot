"""Celery Worker 中执行覆盖分析和缺失测试用例生成的业务服务。"""

from __future__ import annotations

import json
from math import ceil

from app.agents.case_generation_graph import (
    CASE_GENERATION_GRAPH,
    CaseGenerationContext,
    CaseGenerationState,
)
from app.agents.case_generation_schemas import CaseGenerationOutput, GeneratedTestCase
from app.core.config import settings
from app.core.constants import (
    AIModelTaskType,
    CaseGenerationTaskStatus,
    CaseReviewAction,
    RequirementCoverageType,
    RequirementStatus,
    TestCaseSource,
    TestCaseStatus,
)
from app.exceptions import (
    BadRequestException,
    BusinessException,
    ExternalServiceException,
    InternalServerException,
)
from app.models import (
    AIModel,
    CaseGenerationTask,
    CaseReviewRecord,
    PromptTemplate,
    RequirementCaseLink,
    TestCase,
    TestCaseStep,
)
from app.models.mixins import utc_now
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.test_cases_repository import TestCasesRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.services.case_coverage_service import CaseCoverageService


class CaseGenerationExecutionService:
    """执行异步测试用例生成任务，并维护可轮询、可恢复的任务状态。

    功能：领取任务、重新分析覆盖、检索历史用例、运行 LangGraph、保存草稿和审核记录。
    作用：它是 Celery Worker 的核心业务入口，把同步 API 创建的 PENDING 任务推进到
    WAITING_REVIEW、COMPLETED 或 FAILED。
    为什么用它：耗时模型调用不应占用 HTTP 连接；单独执行 Service 还能让 Worker
    使用自己的数据库 Session，并通过状态机和事务实现重复消息幂等。
    """

    def __init__(
        self,
        repository: TestCasesRepository,
        requirements_repository: RequirementsRepository,
        ai_model_repository: AIModelRepository,
        prompt_template_repository: PromptTemplateRepository,
        coverage_service: CaseCoverageService,
    ) -> None:
        self.repository = repository
        self.requirements_repository = requirements_repository
        self.ai_model_repository = ai_model_repository
        self.prompt_template_repository = prompt_template_repository
        self.coverage_service = coverage_service

    async def _load_ai_configuration(self) -> tuple[AIModel, PromptTemplate]:
        """读取并校验生成用例所需的模型和 Prompt。

        功能：校验默认模型、服务商、任务能力及 ``test_case_generation`` 模板。
        作用：在进入 Graph 前一次性建立稳定的运行配置，并把配置 ID 写入任务审计。
        为什么用它：把配置错误前置，可返回明确原因；数据库配置允许管理员换模型，
        固定 Prompt 业务编码则保证运行变量契约不会随名称变化。
        """
        model = await self.ai_model_repository.get_default_model()
        if model is None or not model.enabled:
            raise InternalServerException("未配置已启用的默认测试用例生成模型")
        if not model.provider.enabled:
            raise InternalServerException("默认测试用例生成模型的服务商已停用")
        if AIModelTaskType.TEST_CASE_GENERATION.value not in model.task_types:
            raise InternalServerException("默认模型不支持测试用例生成")
        prompt = await self.prompt_template_repository.get_by_code(
            "test_case_generation"
        )
        if prompt is None or not prompt.enabled:
            raise InternalServerException(
                "未配置已启用的 test_case_generation Prompt"
            )
        return model, prompt

    @staticmethod
    def _gap_to_prompt(row: object) -> dict[str, object]:
        """把一个覆盖缺口压缩成模型需要的稳定 JSON 字段。"""
        item = row.requirement_item
        return {
            "requirement_item_id": item.id,
            "title": item.title,
            "description": item.description,
            "item_type": item.item_type.value,
            "priority": item.priority.value,
            "acceptance_criteria": item.acceptance_criteria,
            "coverage_status": str(row.coverage_status),
            "existing_partial_links": [
                {
                    "test_case_id": link.test_case_id,
                    "title": link.test_case_title,
                    "reason": link.evidence.get("reason", ""),
                    "missing_aspects": link.evidence.get("missing_aspects", []),
                }
                for link in row.links
            ],
        }

    @staticmethod
    def _reference_case_to_prompt(test_case: TestCase, score: float) -> dict[str, object]:
        """把历史标准用例转换成生成和判重使用的轻量快照。"""
        return {
            "reference_type": "PUBLISHED_TEST_CASE",
            "id": test_case.id,
            "case_code": test_case.case_code,
            "title": test_case.title,
            "case_type": test_case.case_type,
            "priority": test_case.priority,
            "preconditions": test_case.preconditions,
            "expected_summary": test_case.expected_summary,
            "retrieval_score": round(score, 4),
            "steps": [
                {
                    "step_no": step.step_no,
                    "action": step.action,
                    "test_data": step.test_data,
                    "expected_result": step.expected_result,
                }
                for step in sorted(test_case.steps, key=lambda value: value.step_no)
            ],
        }

    @staticmethod
    def _knowledge_chunk_to_prompt(chunk: dict[str, object]) -> dict[str, object]:
        """把标准用例知识切片转换成模型可复用、可追溯的参考资料。

        功能：保留文档、章节、页码、正文和检索分数，并明确标记资料类型。
        作用：与正式 test_cases 参考用例一起传给生成 Graph；模型可以借鉴正文，
        同时通过 source_knowledge_chunk_ids 回传真实知识切片来源。
        为什么用它：知识文档格式不一定统一，过早用正则硬拆步骤容易误判；把已经
        检索到的小段证据结构化后交给生成模型，可复用业务内容，又由 Pydantic 和
        ID 白名单约束最终结果。后续若增加专用抽取模型，仍可输出相同结构。
        """
        return {
            "reference_type": "STANDARD_CASE_KNOWLEDGE",
            "knowledge_chunk_id": chunk["chunk_id"],
            "document_id": chunk["document_id"],
            "document_title": chunk["document_title"],
            "section_title": chunk["section_title"],
            "page_no": chunk["page_no"],
            "content": chunk["content"],
            "retrieval_score": round(float(chunk["retrieval_score"]), 4),
        }

    async def _collect_reference_cases(
        self,
        project_id: int,
        module_id: int | None,
        gaps: list[dict[str, object]],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """按每个缺口召回历史标准用例，并同时构造 Graph 判重签名。

        功能：逐缺口调用 PostgreSQL 相似检索，再按用例 ID 去重并保留最高分。
        作用：历史用例既给模型提供格式与业务参考，也用于确定性重复检查。
        为什么用它：先召回 Top-K 而不是把全库塞入 Prompt，可控制 Token 和延迟；
        去重避免同一历史用例因命中多个需求点被重复发送。
        """
        unique_cases: dict[int, tuple[TestCase, float]] = {}
        unique_chunks: dict[int, dict[str, object]] = {}
        for gap in gaps:
            query_text = " ".join(
                str(gap.get(field, ""))
                for field in ("title", "description", "acceptance_criteria")
                if gap.get(field)
            )
            for test_case, score in await self.repository.search_published_cases(
                project_id,
                query_text,
                module_id,
                limit=10,
            ):
                previous = unique_cases.get(test_case.id)
                if previous is None or score > previous[1]:
                    unique_cases[test_case.id] = (test_case, score)
            # 只有项目中存在 READY 的 STANDARD_CASE 文档时才会返回资料；空结果
            # 不触发额外 AI 调用，直接沿用正式用例库 + AI 补缺流程。
            for chunk in await self.repository.search_standard_case_chunks(
                project_id,
                query_text,
                module_id,
                limit=10,
            ):
                chunk_id = int(chunk["chunk_id"])
                previous_chunk = unique_chunks.get(chunk_id)
                if previous_chunk is None or float(chunk["retrieval_score"]) > float(
                    previous_chunk["retrieval_score"]
                ):
                    unique_chunks[chunk_id] = chunk

        # 一个缺口最多召回 10 条，多个缺口合并后可能让 Prompt 再次膨胀。
        # 这里只保留整批中相关度最高的 20 条，兼顾参考价值和输入 Token。
        ranked_cases = sorted(
            unique_cases.values(),
            key=lambda item: item[1],
            reverse=True,
        )[:20]
        case_references = [
            self._reference_case_to_prompt(test_case, score)
            for test_case, score in ranked_cases
        ]
        ranked_chunks = sorted(
            unique_chunks.values(),
            key=lambda item: float(item["retrieval_score"]),
            reverse=True,
        )[:20]
        knowledge_references = [
            self._knowledge_chunk_to_prompt(chunk)
            for chunk in ranked_chunks
        ]
        references = [*case_references, *knowledge_references]
        signatures = [
            {
                "case_id": reference["id"],
                "signature": " ".join(
                    [
                        str(reference["title"]),
                        str(reference["preconditions"]),
                        str(reference["expected_summary"]),
                        *[
                            f"{step['action']} {step['expected_result']}"
                            for step in reference["steps"]
                        ],
                    ]
                ),
            }
            for reference in case_references
        ]
        return references, signatures

    @staticmethod
    def _generated_case_signature(
        generated_case: GeneratedTestCase,
    ) -> dict[str, object]:
        """构造已生成用例的判重签名，供后续批次检查跨批次重复。"""
        return {
            "case_id": generated_case.local_id,
            "signature": " ".join(
                [
                    generated_case.title,
                    generated_case.preconditions,
                    generated_case.expected_summary,
                    *[step.action for step in generated_case.steps],
                    *[step.expected_result for step in generated_case.steps],
                ]
            ),
        }

    async def _generate_case_batches(
        self,
        *,
        task: CaseGenerationTask,
        project_id: int,
        module_id: int | None,
        gaps: list[dict[str, object]],
        model: AIModel,
        prompt: PromptTemplate,
    ) -> tuple[CaseGenerationOutput, list[dict[str, object]], int, int]:
        """分批生成并校验缺失用例，避免单次超长 JSON 被模型截断。

        功能：按配置切分需求缺口，每批独立召回参考用例、运行 Graph，并合并输出。
        作用：替代原来“一次处理全部缺口”的模型调用，同时在批次完成后更新进度。
        为什么用它：模型最大输出 Token 是硬上限，继续调大不能稳定解决长 JSON；
        分批能限制单次输入输出规模，失败时也能明确定位到具体批次。所有批次成功后
        才统一保存草稿，因此不会产生只有部分批次落库的半成品。
        """
        batch_size = settings.case_generation_batch_size
        batch_count = ceil(len(gaps) / batch_size)
        generated_cases: list[GeneratedTestCase] = []
        generated_signatures: list[dict[str, object]] = []
        all_references: dict[str, dict[str, object]] = {}
        warnings: list[str] = []
        total_retry_count = 0

        for batch_index, start in enumerate(
            range(0, len(gaps), batch_size),
            start=1,
        ):
            batch_gaps = gaps[start : start + batch_size]
            references, historical_signatures = (
                await self._collect_reference_cases(
                    project_id,
                    module_id,
                    batch_gaps,
                )
            )
            for reference in references:
                if reference["reference_type"] == "PUBLISHED_TEST_CASE":
                    reference_key = f"case:{int(reference['id'])}"
                else:
                    reference_key = (
                        f"chunk:{int(reference['knowledge_chunk_id'])}"
                    )
                all_references[reference_key] = reference

            initial_state: CaseGenerationState = {
                "gaps_json": json.dumps(batch_gaps, ensure_ascii=False),
                "reference_cases_json": json.dumps(
                    references,
                    ensure_ascii=False,
                ),
                "generation_output": None,
                "validation_feedback": "",
                "validation_errors": [],
                "retry_count": 0,
                "allowed_requirement_item_ids": [
                    int(gap["requirement_item_id"])
                    for gap in batch_gaps
                ],
                "allowed_source_case_ids": [
                    int(reference["id"])
                    for reference in references
                    if reference["reference_type"] == "PUBLISHED_TEST_CASE"
                ],
                "allowed_source_knowledge_chunk_ids": [
                    int(reference["knowledge_chunk_id"])
                    for reference in references
                    if reference["reference_type"] == "STANDARD_CASE_KNOWLEDGE"
                ],
                # 除历史标准用例外，还要把前面批次已接受的用例加入判重范围。
                "existing_case_signatures": [
                    *historical_signatures,
                    *generated_signatures,
                ],
            }
            graph_context = CaseGenerationContext(
                ai_model_repository=self.ai_model_repository,
                ai_model=model,
                prompt_template=prompt,
                usage_context=AIUsageContextDTO(
                    user_id=task.requested_by,
                    project_id=project_id,
                    task_id=str(task.id),
                    retrieval_hit_count=len(references),
                ),
            )
            graph_result = await CASE_GENERATION_GRAPH.ainvoke(
                initial_state,
                context=graph_context,
            )
            batch_output = graph_result.get("generation_output")
            if not isinstance(batch_output, CaseGenerationOutput):
                errors = graph_result.get("validation_errors", [])
                detail = "；".join(str(error) for error in errors[:5])
                raise ExternalServiceException(
                    f"第 {batch_index}/{batch_count} 批测试用例多次生成失败"
                    + (f"：{detail}" if detail else "")
                )
            if not batch_output.cases:
                raise ExternalServiceException(
                    f"第 {batch_index}/{batch_count} 批没有生成任何测试用例"
                )

            # 不同批次的模型可能重复返回 case-1 之类的 local_id。
            # 落库前改成全任务唯一、可追踪批次的本地编号。
            for case_index, generated_case in enumerate(
                batch_output.cases,
                start=1,
            ):
                unique_case = generated_case.model_copy(
                    update={
                        "local_id": (
                            f"batch-{batch_index}-case-{case_index}"
                        )
                    }
                )
                generated_cases.append(unique_case)
                generated_signatures.append(
                    self._generated_case_signature(unique_case)
                )
            warnings.extend(batch_output.warnings)
            total_retry_count += int(graph_result.get("retry_count", 0))

            # 生成阶段占 55%～80%。每批提交一次后，前端轮询能看到真实推进，
            # 不会在多次模型调用期间一直停留在 55%。
            processed_gap_count = min(start + batch_size, len(gaps))
            task.current_stage = (
                f"GENERATING_CASES_{batch_index}_OF_{batch_count}"
            )
            task.progress = 55 + int(
                processed_gap_count / len(gaps) * 25
            )
            await self.repository.commit()

        merged_output = CaseGenerationOutput(
            cases=generated_cases,
            # 输出模型最多允许 100 条警告；去重后截断，避免合并时再次校验失败。
            warnings=list(dict.fromkeys(warnings))[:100],
        )
        return (
            merged_output,
            list(all_references.values()),
            total_retry_count,
            batch_count,
        )

    @staticmethod
    def _generated_case_snapshot(
        generated_case: GeneratedTestCase,
        case_code: str,
    ) -> dict[str, object]:
        """生成不依赖 ORM 关系加载的审核快照。"""
        return {
            "case_code": case_code,
            **generated_case.model_dump(mode="json"),
            "status": TestCaseStatus.DRAFT.value,
            "source": TestCaseSource.AI_GENERATED.value,
        }

    async def _save_drafts(
        self,
        task: CaseGenerationTask,
        generation_output: CaseGenerationOutput,
        module_id: int | None,
    ) -> list[int]:
        """将通过 Graph 校验的结果保存为待人工审核草稿。

        功能：创建用例主表、步骤、需求覆盖关系和 SUBMIT 审核记录。
        作用：把不可信模型输出转换成已经通过白名单校验、可追溯的正式数据库草稿。
        为什么用它：所有相关记录在一个事务提交，任一外键或约束失败都会整体回滚；
        AI 结果只进入 DRAFT，不直接发布，保留人在回路中的质量闸门。
        """
        created_ids: list[int] = []
        for index, generated_case in enumerate(generation_output.cases, start=1):
            case_code = f"AI-{task.id}-{index:03d}"
            test_case = TestCase(
                project_id=task.project_id,
                module_id=module_id,
                case_code=case_code,
                title=generated_case.title,
                case_type=generated_case.case_type.value,
                priority=generated_case.priority.value,
                preconditions=generated_case.preconditions,
                expected_summary=generated_case.expected_summary,
                status=TestCaseStatus.DRAFT.value,
                source=TestCaseSource.AI_GENERATED.value,
                automatable=generated_case.automatable,
                version=1,
                case_metadata={
                    "generation_task_id": task.id,
                    "generation_reason": generated_case.generation_reason,
                    "source_case_ids": generated_case.source_case_ids,
                    "source_knowledge_chunk_ids": (
                        generated_case.source_knowledge_chunk_ids
                    ),
                    "confidence": generated_case.confidence,
                    "tags": generated_case.tags,
                },
                created_by=task.requested_by,
                updated_by=task.requested_by,
            )
            self.repository.add(test_case)
            await self.repository.flush()
            created_ids.append(test_case.id)

            for step in generated_case.steps:
                self.repository.add(
                    TestCaseStep(
                        test_case_id=test_case.id,
                        step_no=step.step_no,
                        action=step.action,
                        test_data=step.test_data,
                        expected_result=step.expected_result,
                    )
                )
            for requirement_item_id in generated_case.requirement_item_ids:
                self.repository.add(
                    RequirementCaseLink(
                        requirement_item_id=requirement_item_id,
                        test_case_id=test_case.id,
                        coverage_type=RequirementCoverageType.FULL.value,
                        confidence=generated_case.confidence,
                        evidence={
                            "source": "AI_GENERATION",
                            "generation_task_id": task.id,
                            "reason": generated_case.generation_reason,
                            "source_case_ids": generated_case.source_case_ids,
                            "source_knowledge_chunk_ids": (
                                generated_case.source_knowledge_chunk_ids
                            ),
                        },
                        created_by=task.requested_by,
                    )
                )
            self.repository.add(
                CaseReviewRecord(
                    test_case_id=test_case.id,
                    generation_task_id=task.id,
                    reviewer_id=None,
                    action=CaseReviewAction.SUBMIT.value,
                    comment="AI 生成完成，等待人工审核",
                    before_data=None,
                    after_data=self._generated_case_snapshot(
                        generated_case,
                        case_code,
                    ),
                )
            )
        await self.repository.flush()
        return created_ids

    async def _mark_failed(
        self,
        project_id: int,
        task_id: int,
        exc: Exception,
    ) -> None:
        """回滚失败事务，并把仍在运行的任务推进到 FAILED。

        功能：重新锁定任务，写入脱敏错误、失败阶段和结束时间。
        作用：保证模型、Graph 或落库任一步异常后，前端不会永久停在 RUNNING。
        为什么用它：数据库异常会让当前事务失效，必须先 rollback；只更新 RUNNING
        可避免覆盖并发取消或已经完成的最终状态。
        """
        await self.repository.rollback()
        task = await self.repository.get_generation_task(
            project_id,
            task_id,
            lock=True,
        )
        # 领取阶段本身也可能失败，例如数据库连接异常。此时任务还停在
        # PENDING；允许把 PENDING 和 RUNNING 都收口为 FAILED，避免页面永久
        # 显示“等待执行”。其他终态仍不能覆盖。
        if task is None or task.status not in {
            CaseGenerationTaskStatus.PENDING.value,
            CaseGenerationTaskStatus.RUNNING.value,
        }:
            await self.repository.rollback()
            return
        task.status = CaseGenerationTaskStatus.FAILED.value
        task.current_stage = "FAILED"
        task.error_message = (
            exc.message
            if isinstance(exc, BusinessException)
            else f"测试用例生成失败：{type(exc).__name__}"
        )
        task.finished_at = utc_now()
        await self.repository.commit()

    async def execute(self, project_id: int, task_id: int) -> bool:
        """领取并完整执行一次缺失测试用例生成任务。

        功能：按阶段更新进度，执行覆盖分析、历史检索、Graph 生成和草稿落库。
        作用：这是 Celery Task 唯一调用入口；返回 False 表示重复或终态消息无需处理。
        为什么用它：每个长阶段前提交进度便于轮询和故障定位；最终草稿批次在单一
        事务中保存，保证任务状态、步骤、覆盖关系和审核记录一致。
        """
        try:
            # 领取也放入统一异常处理范围。这样数据库连接等问题发生在状态推进前，
            # _mark_failed 仍有机会把 PENDING 任务收口，而不是永久卡住。
            task = await self.repository.claim_generation_task(project_id, task_id)
            if task is None:
                return False

            requirement = await self.requirements_repository.get_requirement_detail(
                project_id,
                task.requirement_id,
            )
            if requirement is None:
                raise BadRequestException("生成任务关联的需求不存在")
            if requirement.status != RequirementStatus.CONFIRMED.value:
                raise BadRequestException("生成期间需求已不再是已确认状态")
            submitted_version = str(task.input_snapshot.get("requirement_version", ""))
            if submitted_version and requirement.version != submitted_version:
                raise BadRequestException("需求版本已变化，请重新提交用例生成任务")

            task.current_stage = "ANALYZING_COVERAGE"
            task.progress = 15
            await self.repository.commit()
            coverage_result = await self.coverage_service.analyze(
                requirement,
                user_id=task.requested_by,
                task_id=str(task.id),
            )
            task.retrieval_snapshot = coverage_result.retrieval_snapshot

            gap_rows = [
                row
                for row in coverage_result.matrix.rows
                if row.coverage_status != RequirementCoverageType.FULL.value
            ]
            if not gap_rows:
                task.status = CaseGenerationTaskStatus.COMPLETED.value
                task.current_stage = "NO_GAPS"
                task.progress = 100
                task.output_snapshot = {
                    "generated_case_count": 0,
                    "reason": "覆盖分析后没有缺口",
                }
                task.finished_at = utc_now()
                await self.repository.commit()
                return True

            gaps = [self._gap_to_prompt(row) for row in gap_rows]
            task.current_stage = "RETRIEVING_REFERENCE_CASES"
            task.progress = 35
            await self.repository.commit()

            model, prompt = await self._load_ai_configuration()
            task.model_id = model.id
            task.prompt_template_id = prompt.id
            task.current_stage = "GENERATING_CASES"
            task.progress = 55
            await self.repository.commit()
            (
                generation_output,
                references,
                total_retry_count,
                batch_count,
            ) = await self._generate_case_batches(
                task=task,
                project_id=project_id,
                module_id=requirement.module_id,
                gaps=gaps,
                model=model,
                prompt=prompt,
            )
            task.retrieval_snapshot = {
                **task.retrieval_snapshot,
                "generation_reference_cases": [
                    {
                        "reference_type": reference["reference_type"],
                        "test_case_id": reference.get("id"),
                        "knowledge_chunk_id": reference.get(
                            "knowledge_chunk_id"
                        ),
                        "document_id": reference.get("document_id"),
                        "score": reference["retrieval_score"],
                    }
                    for reference in references
                ],
            }

            task.current_stage = "SAVING_DRAFTS"
            task.progress = 85
            await self.repository.commit()
            created_ids = await self._save_drafts(
                task,
                generation_output,
                requirement.module_id,
            )
            task.status = CaseGenerationTaskStatus.WAITING_REVIEW.value
            task.current_stage = "WAITING_REVIEW"
            task.progress = 100
            task.output_snapshot = {
                "generated_case_count": len(created_ids),
                "test_case_ids": created_ids,
                "warnings": generation_output.warnings,
                "retry_count": total_retry_count,
                "batch_count": batch_count,
                "batch_size": settings.case_generation_batch_size,
                "structured_output": generation_output.model_dump(mode="json"),
            }
            # WAITING_REVIEW 不是最终完成，因此 finished_at 留空；最后一条草稿被
            # 审核后，审核 Service 会把任务改成 COMPLETED 并填写结束时间。
            await self.repository.commit()
            return True
        except Exception as exc:
            await self._mark_failed(project_id, task_id, exc)
            raise
