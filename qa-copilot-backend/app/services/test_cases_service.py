"""测试用例 CRUD、覆盖分析、生成任务提交和人工审核业务服务。"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.automation.definition_factory import (
    build_automation_definition_from_test_case,
)
from app.core.constants import (
    CaseGenerationTaskStatus,
    CaseReviewAction,
    RequirementCoverageType,
    RequirementStatus,
    TestCaseSource,
    TestCaseStatus,
    TestCaseType,
)
from app.exceptions import (
    BadRequestException,
    ConflictException,
    InternalServerException,
    NotFoundException,
)
from app.mappers.test_cases import generation_task_to_vo, test_case_to_vo
from app.models import (
    CaseGenerationTask,
    CaseReviewRecord,
    RequirementCaseLink,
    TestCase,
    TestCaseStep,
    User,
)
from app.models.mixins import utc_now
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.test_cases_repository import TestCasesRepository
from app.repositories.test_modules_repository import TestModulesRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.dto.test_cases import (
    CaseBatchReviewDTO,
    CaseReviewDTO,
    TestCaseCreateDTO,
)
from app.schemas.vo.test_cases import (
    CaseGenerationTaskVO,
    CoverageMatrixVO,
    TestCaseRequirementItemOptionVO,
    TestCaseVO,
)
from app.services.case_coverage_service import CaseCoverageService
from app.workers.case_generation_dispatcher import enqueue_case_generation


class TestCasesService:
    """编排用例 CRUD、覆盖分析、生成和人工审核。

    功能：执行项目权限、状态机、关联校验和事务提交，再调用 Repository 或覆盖服务。
    作用：它是同步 API 的业务入口；Celery Worker 使用独立执行 Service，避免把 HTTP
    用户依赖带入后台任务。
    为什么用它：状态转换和数据权限集中在 Service 可防止 API、脚本和未来批量入口
    各写一套规则。Repository 只处理 SQL，便于分别测试业务和查询。
    """

    def __init__(
        self,
        repository: TestCasesRepository,
        project_repository: TestProjectsRepository,
        module_repository: TestModulesRepository,
        requirement_repository: RequirementsRepository,
        coverage_service: CaseCoverageService,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.module_repository = module_repository
        self.requirement_repository = requirement_repository
        self.coverage_service = coverage_service

    async def _require_project(self, project_id: int, current_user: User) -> None:
        """校验当前用户可访问项目，统一模块的数据权限边界。"""
        project = await self.project_repository.get_accessible_project(
            project_id,
            current_user,
        )
        if project is None:
            raise NotFoundException("项目不存在或无权访问")

    async def _validate_module(self, project_id: int, module_id: int | None) -> None:
        """校验可选模块属于当前项目，防止跨项目关联。"""
        if module_id is None:
            return
        module = await self.module_repository.get_module(project_id, module_id)
        if module is None:
            raise NotFoundException("功能模块不存在或不属于当前项目")

    async def _validate_requirement_item_ids(
        self,
        project_id: int,
        item_ids: list[int],
    ) -> list[int]:
        """校验需求点存在、属于当前项目且调用方没有重复传 ID。"""
        unique_ids = list(dict.fromkeys(item_ids))
        items = await self.repository.list_project_requirement_items_by_ids(
            project_id,
            unique_ids,
        )
        if len(items) != len(unique_ids):
            raise BadRequestException("部分需求点不存在或不属于当前项目")
        return unique_ids

    async def _replace_steps(
        self,
        test_case: TestCase,
        payload: TestCaseCreateDTO,
    ) -> None:
        """整体替换测试步骤并验证步骤编号唯一、连续。

        功能：删除旧步骤，按 DTO 顺序重建新步骤。
        作用：保证前端拖动、增加或删除步骤后，数据库与当前表单完全一致。
        为什么用它：步骤通常作为一个聚合整体编辑，差量比较收益小且容易留下脏数据；
        先删后写配合同一事务，失败时可整体回滚。
        """
        step_numbers = [step.step_no for step in payload.steps]
        expected_numbers = list(range(1, len(payload.steps) + 1))
        if step_numbers != expected_numbers:
            raise BadRequestException("测试步骤编号必须从 1 开始连续递增")
        await self.repository.delete_steps(test_case.id)
        await self.repository.flush()
        for step in payload.steps:
            self.repository.add(
                TestCaseStep(
                    test_case_id=test_case.id,
                    step_no=step.step_no,
                    action=step.action,
                    test_data=step.test_data,
                    expected_result=step.expected_result,
                )
            )

    async def _replace_manual_links(
        self,
        test_case: TestCase,
        requirement_item_ids: list[int],
        user_id: int,
    ) -> None:
        """整体替换用例关联的需求点，并将人工关联记为 FULL 覆盖。"""
        validated_ids = await self._validate_requirement_item_ids(
            test_case.project_id,
            requirement_item_ids,
        )
        await self.repository.delete_case_links(test_case.id)
        await self.repository.flush()
        for requirement_item_id in validated_ids:
            self.repository.add(
                RequirementCaseLink(
                    requirement_item_id=requirement_item_id,
                    test_case_id=test_case.id,
                    coverage_type=RequirementCoverageType.FULL.value,
                    confidence=1,
                    evidence={"source": "MANUAL", "reason": "人工关联测试用例"},
                    created_by=user_id,
                )
            )

    async def list_test_cases(
        self,
        project_id: int,
        current_user: User,
        keyword: str,
        module_id: int | None,
        status: TestCaseStatus | None,
        source: TestCaseSource | None,
        current: int,
        size: int,
    ) -> tuple[list[TestCaseVO], int]:
        """分页返回当前用户可访问项目中的测试用例。"""
        await self._require_project(project_id, current_user)
        records, total = await self.repository.list_test_cases(
            project_id,
            keyword.strip(),
            module_id,
            status,
            source,
            current,
            size,
        )
        item_ids_by_case = await self.repository.list_requirement_item_ids_for_cases(
            [record.id for record in records]
        )
        return [
            test_case_to_vo(record, item_ids_by_case.get(record.id, []))
            for record in records
        ], total

    async def list_requirement_item_options(
        self,
        project_id: int,
        current_user: User,
    ) -> list[TestCaseRequirementItemOptionVO]:
        """返回人工创建或编辑用例时可关联的已确认需求点。"""
        await self._require_project(project_id, current_user)
        items = await self.repository.list_confirmed_project_requirement_items(
            project_id
        )
        return [
            TestCaseRequirementItemOptionVO(
                id=item.id,
                requirement_id=item.requirement_id,
                requirement_title=item.requirement.title,
                item_code=item.item_code,
                title=item.title,
                item_type=item.item_type,
                priority=item.priority,
            )
            for item in items
        ]

    async def get_test_case(
        self,
        project_id: int,
        test_case_id: int,
        current_user: User,
    ) -> TestCaseVO:
        """返回一条测试用例、步骤和需求点关联。"""
        await self._require_project(project_id, current_user)
        test_case = await self.repository.get_test_case(project_id, test_case_id)
        if test_case is None:
            raise NotFoundException("测试用例不存在")
        item_ids = await self.repository.list_case_requirement_item_ids(test_case.id)
        return test_case_to_vo(test_case, item_ids)

    async def create_test_case(
        self,
        project_id: int,
        payload: TestCaseCreateDTO,
        current_user: User,
    ) -> TestCaseVO:
        """创建人工测试用例、步骤和需求覆盖关系。

        功能：校验项目/模块/需求点，创建主记录后生成编码并整体保存步骤与关联。
        作用：为历史标准用例库提供人工资产入口；新用例保持 DRAFT，不能绕过审核
        直接成为标准用例。
        为什么用它：主记录、步骤和覆盖关系在同一事务中提交，可避免出现只有主表
        没有步骤的半成品；数据库唯一约束负责并发下最终防重。
        """
        await self._require_project(project_id, current_user)
        await self._validate_module(project_id, payload.module_id)
        await self._validate_requirement_item_ids(
            project_id,
            payload.requirement_item_ids,
        )
        test_case = TestCase(
            project_id=project_id,
            module_id=payload.module_id,
            case_code=payload.case_code,
            title=payload.title,
            case_type=payload.case_type.value,
            priority=payload.priority.value,
            preconditions=payload.preconditions,
            expected_summary=payload.expected_summary,
            status=TestCaseStatus.DRAFT.value,
            source=TestCaseSource.MANUAL.value,
            automatable=payload.automatable,
            version=payload.version,
            case_metadata=payload.metadata,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        self.repository.add(test_case)
        try:
            await self.repository.flush()
            if not test_case.case_code:
                test_case.case_code = f"TC-{project_id}-{test_case.id:06d}"
            await self._replace_steps(test_case, payload)
            await self._replace_manual_links(
                test_case,
                payload.requirement_item_ids,
                current_user.id,
            )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("项目内测试用例编码已存在，或步骤编号重复") from exc
        created = await self.repository.get_test_case(project_id, test_case.id)
        if created is None:
            raise InternalServerException("测试用例创建后读取失败")
        item_ids = await self.repository.list_case_requirement_item_ids(created.id)
        return test_case_to_vo(created, item_ids)

    async def update_test_case(
        self,
        project_id: int,
        test_case_id: int,
        payload: TestCaseCreateDTO,
        current_user: User,
    ) -> TestCaseVO:
        """整体更新未发布测试用例、步骤和需求点关联。"""
        await self._require_project(project_id, current_user)
        await self._validate_module(project_id, payload.module_id)
        test_case = await self.repository.get_test_case(
            project_id,
            test_case_id,
            lock=True,
        )
        if test_case is None:
            raise NotFoundException("测试用例不存在")
        if test_case.status in {
            TestCaseStatus.PUBLISHED.value,
            TestCaseStatus.DISABLED.value,
        }:
            raise BadRequestException("已发布或已停用用例不能直接编辑，请创建新版本")
        test_case.module_id = payload.module_id
        test_case.case_code = payload.case_code or test_case.case_code
        test_case.title = payload.title
        test_case.case_type = payload.case_type.value
        test_case.priority = payload.priority.value
        test_case.preconditions = payload.preconditions
        test_case.expected_summary = payload.expected_summary
        test_case.automatable = payload.automatable
        test_case.version = payload.version
        test_case.case_metadata = payload.metadata
        test_case.updated_by = current_user.id
        try:
            await self._replace_steps(test_case, payload)
            await self._replace_manual_links(
                test_case,
                payload.requirement_item_ids,
                current_user.id,
            )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("项目内测试用例编码已存在，或步骤编号重复") from exc
        updated = await self.repository.get_test_case(project_id, test_case.id)
        if updated is None:
            raise InternalServerException("测试用例更新后读取失败")
        item_ids = await self.repository.list_case_requirement_item_ids(updated.id)
        return test_case_to_vo(updated, item_ids)

    async def clone_test_case_as_draft(
        self,
        project_id: int,
        test_case_id: int,
        current_user: User,
    ) -> TestCaseVO:
        """把已发布或已停用用例复制成一条可编辑的新草稿。

        功能：复制业务字段、步骤和需求点关系，生成新的用例编码并把版本号加一。
        作用：发布版本保持不可变；用户发现类型、自动化配置或步骤有误时，通过新草稿
        修正，而不是篡改已经参与覆盖计算和自动化审计的旧版本。
        为什么用它：直接编辑已发布记录会让历史执行结果失去对应快照；复制新记录能
        保留旧资产。当前表的用例编码是项目内唯一，因此新草稿生成独立编码，并在
        metadata 中保存来源用例 ID 和原编码作为版本链。
        """
        await self._require_project(project_id, current_user)
        source = await self.repository.get_test_case(
            project_id,
            test_case_id,
            lock=True,
        )
        if source is None:
            raise NotFoundException("测试用例不存在")
        if source.status not in {
            TestCaseStatus.PUBLISHED.value,
            TestCaseStatus.DISABLED.value,
        }:
            raise BadRequestException("只有已发布或已停用用例需要复制为新草稿")

        draft = TestCase(
            project_id=source.project_id,
            module_id=source.module_id,
            case_code=None,
            title=source.title,
            case_type=source.case_type,
            priority=source.priority,
            preconditions=source.preconditions,
            expected_summary=source.expected_summary,
            status=TestCaseStatus.DRAFT.value,
            source=TestCaseSource.MANUAL.value,
            automatable=source.automatable,
            version=source.version + 1,
            case_metadata={
                **source.case_metadata,
                "version_of_test_case_id": source.id,
                "version_of_case_code": source.case_code,
            },
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        self.repository.add(draft)
        try:
            await self.repository.flush()
            draft.case_code = f"TC-{project_id}-{draft.id:06d}"
            for step in sorted(source.steps, key=lambda item: item.step_no):
                self.repository.add(
                    TestCaseStep(
                        test_case_id=draft.id,
                        step_no=step.step_no,
                        action=step.action,
                        test_data=step.test_data,
                        expected_result=step.expected_result,
                    )
                )
            requirement_item_ids = (
                await self.repository.list_case_requirement_item_ids(source.id)
            )
            await self._replace_manual_links(
                draft,
                requirement_item_ids,
                current_user.id,
            )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("新版本用例编码或步骤发生并发冲突，请重试") from exc

        created = await self.repository.get_test_case(project_id, draft.id)
        if created is None:
            raise InternalServerException("新版本测试用例创建后读取失败")
        item_ids = await self.repository.list_case_requirement_item_ids(created.id)
        return test_case_to_vo(created, item_ids)

    async def delete_test_case(
        self,
        project_id: int,
        test_case_id: int,
        current_user: User,
    ) -> None:
        """软删除未发布用例，保留历史生成和审核审计。"""
        await self._require_project(project_id, current_user)
        test_case = await self.repository.get_test_case(
            project_id,
            test_case_id,
            lock=True,
        )
        if test_case is None:
            raise NotFoundException("测试用例不存在")
        if test_case.status == TestCaseStatus.PUBLISHED.value:
            raise BadRequestException("已发布用例不能删除，请先执行停用")
        test_case.deleted_at = utc_now()
        test_case.updated_by = current_user.id
        await self.repository.commit()

    async def get_coverage_matrix(
        self,
        project_id: int,
        requirement_id: int,
        current_user: User,
    ) -> CoverageMatrixVO:
        """查询已保存的覆盖矩阵，不触发模型调用。"""
        await self._require_project(project_id, current_user)
        requirement = await self.requirement_repository.get_requirement_detail(
            project_id,
            requirement_id,
        )
        if requirement is None:
            raise NotFoundException("需求不存在")
        return await self.coverage_service.get_matrix(project_id, requirement_id)

    async def analyze_coverage(
        self,
        project_id: int,
        requirement_id: int,
        current_user: User,
    ) -> CoverageMatrixVO:
        """对已确认需求执行历史检索和覆盖分析并返回最新矩阵。"""
        await self._require_project(project_id, current_user)
        requirement = await self.requirement_repository.get_requirement_detail(
            project_id,
            requirement_id,
        )
        if requirement is None:
            raise NotFoundException("需求不存在")
        if requirement.status != RequirementStatus.CONFIRMED.value:
            raise BadRequestException("只有已确认需求才能执行覆盖分析")
        result = await self.coverage_service.analyze(
            requirement,
            user_id=current_user.id,
        )
        return result.matrix

    async def submit_generation(
        self,
        project_id: int,
        requirement_id: int,
        current_user: User,
        *,
        supervisor_step_id: int | None = None,
    ) -> CaseGenerationTaskVO:
        """只为部分覆盖和未覆盖需求点提交异步生成任务。

        功能：校验需求状态和覆盖缺口，创建可审计任务后投递 Celery。
        作用：API 快速返回任务 ID，前端通过轮询查看进度；耗时模型调用不占用 HTTP。
        为什么用它：任务先落库再投递可让用户立即看到 PENDING 状态；同一需求只允许
        一个活动任务，避免重复生成和并发写入。
        """
        await self._require_project(project_id, current_user)
        # Celery 采用“至少一次投递”，Worker 可能在业务任务创建成功、Supervisor
        # 步骤结果尚未落库时退出。稳定的步骤 ID 是幂等键；重试时直接返回原任务，
        # 不会在旧任务完成后再次生成一批用例。
        if supervisor_step_id is not None:
            existing = await self.repository.get_generation_task_by_supervisor_step(
                supervisor_step_id
            )
            if existing is not None:
                return generation_task_to_vo(existing)
        requirement = await self.requirement_repository.get_requirement_detail(
            project_id,
            requirement_id,
        )
        if requirement is None:
            raise NotFoundException("需求不存在")
        if requirement.status != RequirementStatus.CONFIRMED.value:
            raise BadRequestException("只有已确认需求才能生成测试用例")
        active = await self.repository.get_active_generation_task(requirement_id)
        if active is not None:
            raise ConflictException("该需求已有正在执行的用例生成任务")
        matrix = await self.coverage_service.get_matrix(project_id, requirement_id)
        gap_item_ids = [
            row.requirement_item.id
            for row in matrix.rows
            if row.coverage_status != RequirementCoverageType.FULL.value
        ]
        if not gap_item_ids:
            raise BadRequestException("当前需求已完全覆盖，无需生成补充用例")
        task = CaseGenerationTask(
            project_id=project_id,
            requirement_id=requirement_id,
            status=CaseGenerationTaskStatus.PENDING.value,
            progress=0,
            current_stage="QUEUED",
            requested_by=current_user.id,
            supervisor_step_id=supervisor_step_id,
            input_snapshot={
                "requirement_version": requirement.version,
                "gap_requirement_item_ids": gap_item_ids,
                "coverage_summary": {
                    "total": matrix.total_items,
                    "full": matrix.full_count,
                    "partial": matrix.partial_count,
                    "uncovered": matrix.uncovered_count,
                },
            },
        )
        self.repository.add(task)
        try:
            await self.repository.commit()
            celery_task_id = await enqueue_case_generation(project_id, task.id)
            # 当前表没有单独 celery_task_id 列，先保存在稳定输入快照中，既不改变
            # 数据库结构，也能从任务记录追踪 Redis/Celery 消息。
            task.input_snapshot = {
                **task.input_snapshot,
                "celery_task_id": celery_task_id,
            }
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("该需求已有正在执行的用例生成任务") from exc
        except Exception as exc:
            task.status = CaseGenerationTaskStatus.FAILED.value
            task.current_stage = "DISPATCH_FAILED"
            task.error_message = f"任务投递失败：{type(exc).__name__}"
            task.finished_at = utc_now()
            await self.repository.commit()
            raise InternalServerException("用例生成任务投递失败") from exc
        created = await self.repository.get_generation_task(project_id, task.id)
        if created is None:
            raise InternalServerException("生成任务创建后读取失败")
        return generation_task_to_vo(created)

    async def compensate_supervisor_generation(self, supervisor_step_id: int) -> bool:
        """补偿取消尚未开始的 Supervisor 用例生成任务。

        功能：仅将 PENDING 任务改为 CANCELLED；RUNNING 或终态任务不强行覆盖。
        作用：Supervisor 后续步骤失败时调用，尽量撤销前面已经提交但尚未执行的写操作。
        为什么用它：外部 Worker 一旦开始生成就不能假装事务回滚；条件更新保证只取消
        可安全撤销的任务，无法撤销的情况会由 Supervisor 步骤结果明确记录并留给人工处理。
        """
        cancelled = await self.repository.cancel_pending_generation_by_supervisor_step(
            supervisor_step_id
        )
        await self.repository.commit()
        return cancelled

    async def list_generation_tasks(
        self,
        project_id: int,
        current_user: User,
        requirement_id: int | None,
        status: CaseGenerationTaskStatus | None,
        current: int,
        size: int,
    ) -> tuple[list[CaseGenerationTaskVO], int]:
        """分页返回生成任务，并为审核页装配对应草稿用例。"""
        await self._require_project(project_id, current_user)
        tasks, total = await self.repository.list_generation_tasks(
            project_id,
            requirement_id,
            status,
            current,
            size,
        )
        result: list[CaseGenerationTaskVO] = []
        for task in tasks:
            cases = await self.repository.list_generation_task_cases(task.id)
            ids_by_case = await self.repository.list_requirement_item_ids_for_cases(
                [case.id for case in cases]
            )
            result.append(
                generation_task_to_vo(
                    task,
                    [
                        test_case_to_vo(case, ids_by_case.get(case.id, []))
                        for case in cases
                    ],
                )
            )
        return result, total

    @staticmethod
    def _case_snapshot(test_case: TestCase) -> dict[str, object]:
        """生成审核前后快照，避免之后编辑用例导致审计内容变化。"""
        return {
            "id": test_case.id,
            "case_code": test_case.case_code,
            "title": test_case.title,
            "status": test_case.status,
            "version": test_case.version,
            "metadata": test_case.case_metadata,
            "steps": [
                {
                    "step_no": step.step_no,
                    "action": step.action,
                    "test_data": step.test_data,
                    "expected_result": step.expected_result,
                }
                for step in sorted(test_case.steps, key=lambda item: item.step_no)
            ],
        }

    async def _apply_review_action(
        self,
        project_id: int,
        test_case: TestCase,
        payload: CaseReviewDTO,
        current_user: User,
    ) -> None:
        """对一条已经锁定的用例应用审核状态机，但不提交事务。

        功能：校验动作与当前状态，更新用例，保存前后快照，并收口生成任务。
        作用：单条审核和批量审核共用这一内部方法，调用方决定何时统一提交。
        为什么用它：如果批量接口循环调用原来的单条方法，每条都会单独提交，后面
        一条失败时前面的状态无法回滚；拆出“不提交”的核心规则可保证整批原子性。
        """
        before = self._case_snapshot(test_case)
        action = payload.action
        allowed_statuses: dict[CaseReviewAction, set[str]] = {
            CaseReviewAction.ACCEPT: {
                TestCaseStatus.DRAFT.value,
                TestCaseStatus.REVIEWING.value,
                TestCaseStatus.REJECTED.value,
            },
            CaseReviewAction.MODIFY: {
                TestCaseStatus.DRAFT.value,
                TestCaseStatus.REVIEWING.value,
                TestCaseStatus.APPROVED.value,
                TestCaseStatus.REJECTED.value,
            },
            CaseReviewAction.REJECT: {
                TestCaseStatus.DRAFT.value,
                TestCaseStatus.REVIEWING.value,
                TestCaseStatus.APPROVED.value,
            },
            CaseReviewAction.DUPLICATE: {
                TestCaseStatus.DRAFT.value,
                TestCaseStatus.REVIEWING.value,
                TestCaseStatus.APPROVED.value,
            },
            CaseReviewAction.PUBLISH: {TestCaseStatus.APPROVED.value},
            CaseReviewAction.DISABLE: {TestCaseStatus.PUBLISHED.value},
        }
        if action not in allowed_statuses or test_case.status not in allowed_statuses[action]:
            raise BadRequestException(
                f"当前用例状态 {test_case.status} 不允许执行 {action.value}"
            )
        if action == CaseReviewAction.PUBLISH and test_case.automatable:
            if test_case.case_type != TestCaseType.API.value:
                raise BadRequestException(
                    "当前用例勾选了“适合自动化”，但测试类型不是“接口测试”。"
                    "请先取消自动化标记，或复制为新草稿后改为接口测试并补充接口模板"
                )
            # 与自动化定义创建共用同一转换器。这里校验通过，发布后才不会再次因为
            # request、assertions 或具体字段格式缺失而被自动化模块拒绝。
            build_automation_definition_from_test_case(test_case)
        if action == CaseReviewAction.ACCEPT:
            test_case.status = TestCaseStatus.APPROVED.value
        elif action == CaseReviewAction.MODIFY:
            test_case.status = TestCaseStatus.DRAFT.value
        elif action in {CaseReviewAction.REJECT, CaseReviewAction.DUPLICATE}:
            test_case.status = TestCaseStatus.REJECTED.value
            if action == CaseReviewAction.DUPLICATE:
                test_case.case_metadata = {
                    **test_case.case_metadata,
                    "duplicate": True,
                    "duplicate_comment": payload.comment,
                }
        elif action == CaseReviewAction.PUBLISH:
            test_case.status = TestCaseStatus.PUBLISHED.value
        elif action == CaseReviewAction.DISABLE:
            test_case.status = TestCaseStatus.DISABLED.value
        test_case.updated_by = current_user.id
        latest_review = await self.repository.get_latest_generation_review(test_case.id)
        generation_task_id = (
            latest_review.generation_task_id if latest_review is not None else None
        )
        self.repository.add(
            CaseReviewRecord(
                test_case_id=test_case.id,
                generation_task_id=generation_task_id,
                reviewer_id=current_user.id,
                action=action.value,
                comment=payload.comment,
                before_data=before,
                after_data=self._case_snapshot(test_case),
            )
        )
        if generation_task_id is not None:
            await self.repository.flush()
            remaining = await self.repository.count_unreviewed_task_cases(
                generation_task_id
            )
            if remaining == 0:
                task = await self.repository.get_generation_task(
                    project_id,
                    generation_task_id,
                    lock=True,
                )
                if task is not None and task.status == CaseGenerationTaskStatus.WAITING_REVIEW.value:
                    task.status = CaseGenerationTaskStatus.COMPLETED.value
                    task.current_stage = "REVIEW_COMPLETED"
                    task.progress = 100
                    task.finished_at = utc_now()

    async def review_test_case(
        self,
        project_id: int,
        test_case_id: int,
        payload: CaseReviewDTO,
        current_user: User,
    ) -> TestCaseVO:
        """按照受控状态机审核单条测试用例。

        功能：锁定指定用例，应用审核动作并提交状态与审核记录。
        作用：提供单条精审入口；复杂修改和重复判断仍通过该入口逐条处理。
        为什么用它：单条与批量复用相同状态机，确保两种入口的业务规则一致。
        """
        await self._require_project(project_id, current_user)
        test_case = await self.repository.get_test_case(
            project_id,
            test_case_id,
            lock=True,
        )
        if test_case is None:
            raise NotFoundException("测试用例不存在")
        await self._apply_review_action(
            project_id,
            test_case,
            payload,
            current_user,
        )
        await self.repository.commit()
        updated = await self.repository.get_test_case(project_id, test_case.id)
        if updated is None:
            raise InternalServerException("审核后读取测试用例失败")
        item_ids = await self.repository.list_case_requirement_item_ids(updated.id)
        return test_case_to_vo(updated, item_ids)

    async def batch_review_test_cases(
        self,
        project_id: int,
        payload: CaseBatchReviewDTO,
        current_user: User,
    ) -> list[TestCaseVO]:
        """在一个事务中批量接受、驳回或发布测试用例。

        功能：一次锁定全部目标用例，逐条复用审核状态机，最后统一提交并返回结果。
        作用：降低大量 AI 草稿的人工点击成本，同时保留每条独立审核记录。
        为什么用它：任何一条状态不允许时整批回滚，比部分成功更容易理解和重试；
        批量修改与判重仍要求单条处理，防止把同一内容错误套用到不同用例。
        """
        await self._require_project(project_id, current_user)
        test_cases = await self.repository.get_test_cases_for_review(
            project_id,
            payload.test_case_ids,
        )
        if len(test_cases) != len(payload.test_case_ids):
            await self.repository.rollback()
            raise NotFoundException("部分测试用例不存在、已删除或不属于当前项目")

        test_cases_by_id = {test_case.id: test_case for test_case in test_cases}
        ordered_cases = [
            test_cases_by_id[test_case_id]
            for test_case_id in payload.test_case_ids
        ]
        try:
            for test_case in ordered_cases:
                await self._apply_review_action(
                    project_id,
                    test_case,
                    payload,
                    current_user,
                )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        item_ids_by_case = (
            await self.repository.list_requirement_item_ids_for_cases(
                payload.test_case_ids
            )
        )
        return [
            test_case_to_vo(
                test_case,
                item_ids_by_case.get(test_case.id, []),
            )
            for test_case in ordered_cases
        ]
