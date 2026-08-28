"""测试用例、覆盖关系、生成任务和审核记录的数据访问层。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.orm import selectinload

from app.core.constants import (
    CaseGenerationTaskStatus,
    KnowledgeDocumentParseStatus,
    KnowledgeDocumentType,
    TestCaseSource,
    TestCaseStatus,
)
from app.models import (
    CaseGenerationTask,
    CaseReviewRecord,
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeDocumentChunk,
    Requirement,
    RequirementCaseLink,
    RequirementItem,
    TestCase,
    TestCaseStep,
)
from app.repositories.base_repository import BaseRepository


class TestCasesRepository(BaseRepository):
    """集中封装测试用例模块使用的 SQLAlchemy 查询。

    功能：提供用例、步骤、覆盖关系、生成任务和审核记录的增删改查方法。
    作用：Service 只负责业务规则，不直接拼 SQL；同步 API 与 Celery Worker 可以
    复用相同的数据访问逻辑和同一个事务边界。
    为什么用它：把查询集中在 Repository 能减少重复 SQL，便于统一增加项目隔离、
    预加载策略和索引优化。替代方案是在 Service 里直接查询，但模块扩大后难维护。
    """

    async def list_test_cases(
        self,
        project_id: int,
        keyword: str,
        module_id: int | None,
        status: TestCaseStatus | None,
        source: TestCaseSource | None,
        current: int,
        size: int,
    ) -> tuple[list[TestCase], int]:
        """分页查询项目内未删除的测试用例。

        功能：按关键词、模块、状态和来源筛选，并返回当前页实体与总数。
        作用：支撑测试用例管理页面；预加载模块、创建人和步骤，避免逐行查询。
        为什么用它：列表和 count 使用相同条件可保证分页总数准确；selectinload
        比循环访问关系产生的 N+1 查询更稳定。
        """
        conditions = [
            TestCase.project_id == project_id,
            TestCase.deleted_at.is_(None),
        ]
        if keyword:
            conditions.append(
                or_(
                    TestCase.case_code.contains(keyword),
                    TestCase.title.contains(keyword),
                    TestCase.preconditions.contains(keyword),
                    TestCase.expected_summary.contains(keyword),
                )
            )
        if module_id is not None:
            conditions.append(TestCase.module_id == module_id)
        if status is not None:
            conditions.append(TestCase.status == status.value)
        if source is not None:
            conditions.append(TestCase.source == source.value)

        total = int(
            await self.session.scalar(select(func.count(TestCase.id)).where(*conditions))
            or 0
        )
        statement = (
            select(TestCase)
            # 更新步骤后，同一 Session 的 identity map 里可能仍保留旧集合；
            # populate_existing 强制用本次查询结果覆盖缓存，保证接口返回新步骤。
            .execution_options(populate_existing=True)
            .options(
                selectinload(TestCase.module),
                selectinload(TestCase.creator),
                selectinload(TestCase.steps),
            )
            .where(*conditions)
            .order_by(TestCase.updated_at.desc(), TestCase.id.desc())
            .offset((current - 1) * size)
            .limit(size)
        )
        records = list((await self.session.scalars(statement)).all())
        return records, total

    async def get_test_case(
        self,
        project_id: int,
        test_case_id: int,
        *,
        lock: bool = False,
    ) -> TestCase | None:
        """查询项目内一条未删除用例及其步骤。

        功能：同时校验 project_id 和 test_case_id，可选对主记录加行锁。
        作用：详情、编辑、删除和审核共享这一入口，防止跨项目读取或修改用例。
        为什么用它：写操作使用 ``FOR UPDATE`` 可避免两个请求同时推进同一用例状态；
        只锁主表而不锁预加载关系，兼顾一致性与锁范围。
        """
        statement = (
            select(TestCase)
            .execution_options(populate_existing=True)
            .options(
                selectinload(TestCase.module),
                selectinload(TestCase.creator),
                selectinload(TestCase.steps),
            )
            .where(
                TestCase.id == test_case_id,
                TestCase.project_id == project_id,
                TestCase.deleted_at.is_(None),
            )
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_test_cases_for_review(
        self,
        project_id: int,
        test_case_ids: Sequence[int],
    ) -> list[TestCase]:
        """锁定并返回同一项目中准备批量审核的全部未删除用例。

        功能：一次查询加载主记录、模块、创建人和步骤，并对主记录加行锁。
        作用：批量审核在校验和修改前调用，保证其他请求不能同时推进这些用例状态。
        为什么用它：逐条查询会产生多次数据库往返，而且锁定顺序不一致容易增加
        并发死锁风险；按 ID 排序后一次锁定更稳定。
        """
        if not test_case_ids:
            return []
        statement = (
            select(TestCase)
            .execution_options(populate_existing=True)
            .options(
                selectinload(TestCase.module),
                selectinload(TestCase.creator),
                selectinload(TestCase.steps),
            )
            .where(
                TestCase.project_id == project_id,
                TestCase.id.in_(test_case_ids),
                TestCase.deleted_at.is_(None),
            )
            .order_by(TestCase.id)
            .with_for_update()
        )
        return list((await self.session.scalars(statement)).all())

    async def claim_generation_task(
        self,
        project_id: int,
        task_id: int,
    ) -> CaseGenerationTask | None:
        """原子领取一条尚未开始的用例生成任务。

        功能：只把指定项目中仍为 PENDING 的任务推进到 RUNNING，并返回任务实体。
        作用：Celery Worker 开始执行前必须先调用它；重复投递或多个 Worker 抢同一
        消息时，只有一个请求能取得返回值。
        为什么用它：先查询再修改存在竞态窗口，单条 UPDATE ... RETURNING 由数据库
        原子判断旧状态，可实现至少一次消息投递下的幂等消费。
        """
        task_id_result = await self.session.scalar(
            update(CaseGenerationTask)
            .where(
                CaseGenerationTask.id == task_id,
                CaseGenerationTask.project_id == project_id,
                CaseGenerationTask.status == CaseGenerationTaskStatus.PENDING.value,
            )
            .values(
                status=CaseGenerationTaskStatus.RUNNING.value,
                current_stage="LOADING_REQUIREMENT",
                progress=5,
                started_at=func.now(),
                error_message=None,
            )
            .returning(CaseGenerationTask.id)
        )
        if task_id_result is None:
            await self.rollback()
            return None
        await self.commit()
        return await self.get_generation_task(project_id, task_id_result)

    async def delete_steps(self, test_case_id: int) -> None:
        """物理删除一条用例的旧步骤，供整体更新时重新写入。

        功能：一次 SQL 清除旧步骤。
        作用：与后续新增步骤处于同一事务，形成“整体替换”的编辑语义。
        为什么用它：先删后 flush 可以避免旧、新步骤同时占用唯一键
        ``(test_case_id, step_no)``；逐条修改更复杂且容易留下已删除步骤。
        """
        await self.session.execute(
            delete(TestCaseStep).where(TestCaseStep.test_case_id == test_case_id)
        )

    async def list_case_requirement_item_ids(self, test_case_id: int) -> list[int]:
        """返回一条用例当前关联的需求点 ID。"""
        result = await self.session.scalars(
            select(RequirementCaseLink.requirement_item_id).where(
                RequirementCaseLink.test_case_id == test_case_id
            )
        )
        return list(result.all())

    async def list_requirement_item_ids_for_cases(
        self,
        test_case_ids: Sequence[int],
    ) -> dict[int, list[int]]:
        """一次查询返回多条用例的需求点关联，避免列表页产生 N+1 SQL。"""
        if not test_case_ids:
            return {}
        rows = (
            await self.session.execute(
                select(
                    RequirementCaseLink.test_case_id,
                    RequirementCaseLink.requirement_item_id,
                ).where(RequirementCaseLink.test_case_id.in_(set(test_case_ids)))
            )
        ).all()
        result: dict[int, list[int]] = {}
        for test_case_id, requirement_item_id in rows:
            result.setdefault(test_case_id, []).append(requirement_item_id)
        return result

    async def delete_case_links(self, test_case_id: int) -> None:
        """删除一条用例的全部需求覆盖关系，供人工整体调整关联。"""
        await self.session.execute(
            delete(RequirementCaseLink).where(
                RequirementCaseLink.test_case_id == test_case_id
            )
        )

    async def list_project_requirement_items_by_ids(
        self,
        project_id: int,
        item_ids: Sequence[int],
    ) -> list[RequirementItem]:
        """查询确实属于当前项目的一组需求点。

        功能：通过 Requirement 主表校验需求点所属项目。
        作用：创建或编辑用例时阻止前端把其他项目的需求点 ID 写入覆盖关系。
        为什么用它：外键只能保证 ID 存在，不能保证项目边界，因此必须增加关联查询。
        """
        if not item_ids:
            return []
        statement = (
            select(RequirementItem)
            .join(Requirement, Requirement.id == RequirementItem.requirement_id)
            .where(
                Requirement.project_id == project_id,
                Requirement.deleted_at.is_(None),
                RequirementItem.id.in_(set(item_ids)),
            )
        )
        return list((await self.session.scalars(statement)).all())

    async def list_confirmed_requirement_items(
        self,
        project_id: int,
        requirement_id: int,
    ) -> list[RequirementItem]:
        """按稳定顺序读取参与覆盖分析的已确认原子需求点。"""
        statement = (
            select(RequirementItem)
            .join(Requirement, Requirement.id == RequirementItem.requirement_id)
            .where(
                Requirement.project_id == project_id,
                Requirement.id == requirement_id,
                Requirement.deleted_at.is_(None),
                RequirementItem.confirmed.is_(True),
            )
            .order_by(RequirementItem.order_no, RequirementItem.id)
        )
        return list((await self.session.scalars(statement)).all())

    async def list_confirmed_project_requirement_items(
        self,
        project_id: int,
    ) -> list[RequirementItem]:
        """返回项目下可供人工用例关联的全部已确认需求点。

        功能：跨该项目的多份需求查询已确认原子需求点，并预加载所属需求。
        作用：测试用例表单使用它展示可读的“需求标题 / 需求点”选项。
        为什么用它：前端不应为每份需求分别发请求；一次关联查询能保证项目隔离，
        且只暴露确认后的稳定需求点。
        """
        statement = (
            select(RequirementItem)
            .join(Requirement, Requirement.id == RequirementItem.requirement_id)
            .options(selectinload(RequirementItem.requirement))
            .where(
                Requirement.project_id == project_id,
                Requirement.deleted_at.is_(None),
                Requirement.status == "CONFIRMED",
                RequirementItem.confirmed.is_(True),
            )
            .order_by(
                Requirement.updated_at.desc(),
                RequirementItem.order_no,
                RequirementItem.id,
            )
        )
        return list((await self.session.scalars(statement)).all())

    async def list_requirement_links(
        self,
        requirement_id: int,
    ) -> list[RequirementCaseLink]:
        """查询需求下全部需求点的有效用例覆盖关系。"""
        statement = (
            select(RequirementCaseLink)
            .join(
                RequirementItem,
                RequirementItem.id == RequirementCaseLink.requirement_item_id,
            )
            .join(TestCase, TestCase.id == RequirementCaseLink.test_case_id)
            .options(
                selectinload(RequirementCaseLink.test_case).selectinload(TestCase.steps),
                selectinload(RequirementCaseLink.test_case).selectinload(TestCase.module),
            )
            .where(
                RequirementItem.requirement_id == requirement_id,
                TestCase.deleted_at.is_(None),
                # 只有已发布用例才是可复用的标准测试资产。DRAFT、APPROVED 或
                # REJECTED 都不能提前把需求点算成已覆盖；发布后同一关联自动生效。
                TestCase.status == TestCaseStatus.PUBLISHED.value,
            )
            .order_by(
                RequirementCaseLink.requirement_item_id,
                RequirementCaseLink.confidence.desc().nullslast(),
            )
        )
        return list((await self.session.scalars(statement)).all())

    async def delete_ai_coverage_links(self, requirement_id: int) -> None:
        """仅清除覆盖分析产生的旧关系，保留人工维护的覆盖证据。

        功能：删除 evidence.source 为 AI_ANALYSIS 的关系。
        作用：重新分析前清理旧算法结果，同时保护人工裁决结果。
        为什么用它：覆盖分析可以重复运行，但人工确认优先级更高；全量删除会让人工
        工作丢失，因此使用证据来源区分机器结果和人工结果。
        """
        item_ids = select(RequirementItem.id).where(
            RequirementItem.requirement_id == requirement_id
        )
        await self.session.execute(
            delete(RequirementCaseLink).where(
                RequirementCaseLink.requirement_item_id.in_(item_ids),
                RequirementCaseLink.evidence["source"].as_string() == "AI_ANALYSIS",
            )
        )

    async def search_published_cases(
        self,
        project_id: int,
        query_text: str,
        module_id: int | None,
        *,
        limit: int = 10,
    ) -> list[tuple[TestCase, float]]:
        """检索同项目内与需求点相似的已发布标准用例。

        功能：使用 PostgreSQL trigram 文本相似度召回候选，并对同模块用例加权。
        作用：为覆盖判断和生成前去重提供较小、相关的候选集，避免把整个用例库
        发送给模型。
        为什么用它：当前表没有独立用例向量列，pg_trgm 可直接复用 PostgreSQL，
        适合首版中文短文本召回；数据规模扩大后可替换为 Embedding + 向量索引，
        Service 和上层工作流无需改变。
        """
        # 与 SQL 中 trigram 表达式索引保持完全一致，PostgreSQL 才能使用索引。
        searchable_text = (
            func.coalesce(TestCase.title, "")
            + " "
            + func.coalesce(TestCase.preconditions, "")
            + " "
            + func.coalesce(TestCase.expected_summary, "")
        )
        lexical_score = func.similarity(searchable_text, query_text)
        module_bonus = (
            case((TestCase.module_id == module_id, 0.15), else_=0.0)
            if module_id is not None
            else 0.0
        )
        final_score = (lexical_score + module_bonus).label("retrieval_score")
        statement = (
            select(TestCase, final_score)
            .options(
                selectinload(TestCase.module),
                selectinload(TestCase.steps),
            )
            .where(
                TestCase.project_id == project_id,
                TestCase.deleted_at.is_(None),
                TestCase.status == TestCaseStatus.PUBLISHED.value,
            )
            .order_by(final_score.desc(), TestCase.updated_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(statement)).all()
        return [(row[0], float(row[1] or 0.0)) for row in rows]

    async def search_standard_case_chunks(
        self,
        project_id: int,
        query_text: str,
        module_id: int | None,
        *,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """检索项目知识库中的标准用例文档切片。

        功能：只从当前项目已启用知识库、READY 文档和 STANDARD_CASE 类型中，
        按标题、章节和正文的 trigram 相似度召回切片，并给同模块资料加权。
        作用：为缺失用例生成补充“数据库正式用例之外”的项目标准用例资料；没有
        标准用例文档时返回空列表，上层会直接跳过，不额外调用模型。
        为什么用它：先在 PostgreSQL 中条件检索可以避免把整个知识库塞进 Prompt；
        返回来源切片 ID 又能让模型生成结果保留到原文的可追溯证据。后续数据量增大
        时可以改成向量召回，Service 的输入输出契约无需变化。
        """
        searchable_text = (
            func.coalesce(KnowledgeDocument.title, "")
            + " "
            + func.coalesce(KnowledgeDocumentChunk.section_title, "")
            + " "
            + func.coalesce(KnowledgeDocumentChunk.content, "")
        )
        lexical_score = func.similarity(searchable_text, query_text)
        module_bonus = (
            case((KnowledgeDocument.module_id == module_id, 0.15), else_=0.0)
            if module_id is not None
            else 0.0
        )
        final_score = (lexical_score + module_bonus).label("retrieval_score")
        statement = (
            select(
                KnowledgeDocumentChunk.id.label("chunk_id"),
                KnowledgeDocument.id.label("document_id"),
                KnowledgeDocument.title.label("document_title"),
                KnowledgeDocumentChunk.section_title,
                KnowledgeDocumentChunk.page_no,
                KnowledgeDocumentChunk.content,
                final_score,
            )
            .select_from(KnowledgeDocumentChunk)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id == KnowledgeDocumentChunk.document_id,
            )
            .join(
                KnowledgeBase,
                KnowledgeBase.id == KnowledgeDocument.knowledge_base_id,
            )
            .where(
                KnowledgeBase.project_id == project_id,
                KnowledgeBase.enabled.is_(True),
                KnowledgeDocument.deleted_at.is_(None),
                KnowledgeDocument.parse_status
                == KnowledgeDocumentParseStatus.READY.value,
                KnowledgeDocument.document_type
                == KnowledgeDocumentType.STANDARD_CASE.value,
            )
            .order_by(final_score.desc(), KnowledgeDocumentChunk.id.asc())
            .limit(limit)
        )
        rows = (await self.session.execute(statement)).mappings().all()
        return [
            {
                "chunk_id": int(row["chunk_id"]),
                "document_id": int(row["document_id"]),
                "document_title": str(row["document_title"]),
                "section_title": row["section_title"],
                "page_no": row["page_no"],
                "content": str(row["content"]),
                "retrieval_score": float(row["retrieval_score"] or 0.0),
            }
            for row in rows
        ]

    async def get_active_generation_task(
        self,
        requirement_id: int,
    ) -> CaseGenerationTask | None:
        """查询同一需求当前排队、运行或等待审核的生成任务。"""
        return await self.session.scalar(
            select(CaseGenerationTask).where(
                CaseGenerationTask.requirement_id == requirement_id,
                CaseGenerationTask.status.in_(
                    [
                        CaseGenerationTaskStatus.PENDING.value,
                        CaseGenerationTaskStatus.RUNNING.value,
                        CaseGenerationTaskStatus.WAITING_REVIEW.value,
                    ]
                ),
            )
        )

    async def get_generation_task_by_supervisor_step(
        self,
        supervisor_step_id: int,
    ) -> CaseGenerationTask | None:
        """按 Supervisor 步骤读取已经创建的生成任务，供重复消息幂等复用。"""
        return await self.session.scalar(
            select(CaseGenerationTask).where(
                CaseGenerationTask.supervisor_step_id == supervisor_step_id
            )
        )

    async def cancel_pending_generation_by_supervisor_step(
        self,
        supervisor_step_id: int,
    ) -> bool:
        """只取消尚未被 Worker 领取的 Supervisor 用例生成任务。"""
        task_id = await self.session.scalar(
            update(CaseGenerationTask)
            .where(
                CaseGenerationTask.supervisor_step_id == supervisor_step_id,
                CaseGenerationTask.status == CaseGenerationTaskStatus.PENDING.value,
            )
            .values(
                status=CaseGenerationTaskStatus.CANCELLED.value,
                current_stage="SUPERVISOR_COMPENSATED",
                error_message="Supervisor 后续步骤失败，任务在执行前已补偿取消",
                finished_at=func.now(),
            )
            .returning(CaseGenerationTask.id)
        )
        return task_id is not None

    async def get_generation_task(
        self,
        project_id: int,
        task_id: int,
        *,
        lock: bool = False,
    ) -> CaseGenerationTask | None:
        """查询项目内生成任务，可选加行锁供 Worker 幂等领取。"""
        statement = (
            select(CaseGenerationTask)
            .options(selectinload(CaseGenerationTask.requirement))
            .where(
                CaseGenerationTask.id == task_id,
                CaseGenerationTask.project_id == project_id,
            )
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_generation_tasks(
        self,
        project_id: int,
        requirement_id: int | None,
        status: CaseGenerationTaskStatus | None,
        current: int,
        size: int,
    ) -> tuple[list[CaseGenerationTask], int]:
        """分页查询生成任务及其需求标题。"""
        conditions = [CaseGenerationTask.project_id == project_id]
        if requirement_id is not None:
            conditions.append(CaseGenerationTask.requirement_id == requirement_id)
        if status is not None:
            conditions.append(CaseGenerationTask.status == status.value)
        total = int(
            await self.session.scalar(
                select(func.count(CaseGenerationTask.id)).where(*conditions)
            )
            or 0
        )
        statement = (
            select(CaseGenerationTask)
            .options(selectinload(CaseGenerationTask.requirement))
            .where(*conditions)
            .order_by(CaseGenerationTask.created_at.desc(), CaseGenerationTask.id.desc())
            .offset((current - 1) * size)
            .limit(size)
        )
        return list((await self.session.scalars(statement)).all()), total

    async def list_generation_task_cases(self, task_id: int) -> list[TestCase]:
        """查询某次生成任务产生并进入审核流程的全部用例。"""
        statement = (
            select(TestCase)
            .join(
                CaseReviewRecord,
                CaseReviewRecord.test_case_id == TestCase.id,
            )
            .options(
                selectinload(TestCase.module),
                selectinload(TestCase.creator),
                selectinload(TestCase.steps),
            )
            .where(
                CaseReviewRecord.generation_task_id == task_id,
                TestCase.deleted_at.is_(None),
            )
            .distinct()
            .order_by(TestCase.id)
        )
        return list((await self.session.scalars(statement)).all())

    async def get_latest_generation_review(
        self,
        test_case_id: int,
    ) -> CaseReviewRecord | None:
        """取得用例最近一次关联生成任务的审核记录。"""
        return await self.session.scalar(
            select(CaseReviewRecord)
            .where(CaseReviewRecord.test_case_id == test_case_id)
            .order_by(CaseReviewRecord.created_at.desc(), CaseReviewRecord.id.desc())
            .limit(1)
        )

    async def count_unreviewed_task_cases(self, task_id: int) -> int:
        """统计生成任务下仍处于草稿或审核中的用例数量。"""
        return int(
            await self.session.scalar(
                select(func.count(func.distinct(TestCase.id)))
                .join(CaseReviewRecord, CaseReviewRecord.test_case_id == TestCase.id)
                .where(
                    CaseReviewRecord.generation_task_id == task_id,
                    TestCase.deleted_at.is_(None),
                    TestCase.status.in_(
                        [TestCaseStatus.DRAFT.value, TestCaseStatus.REVIEWING.value]
                    ),
                )
            )
            or 0
        )
