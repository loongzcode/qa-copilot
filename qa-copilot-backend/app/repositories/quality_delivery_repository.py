"""多 Agent 质量交付协调器所需的只读事实查询。"""

from sqlalchemy import distinct, func, select

from app.core.constants import TestCaseStatus
from app.models import CaseGenerationTask, RequirementCaseLink, RequirementExtractionTask, RequirementItem, TestCase
from app.repositories.base_repository import BaseRepository


class QualityDeliveryRepository(BaseRepository):
    """一次查询一个需求的阶段事实，避免协调器直接依赖多个 ORM 实体。"""

    async def load_facts(self, requirement_id: int) -> dict[str, int | str | None]:
        """读取需求点、任务、审核用例、发布用例和自动化就绪用例数量。"""
        item_count = int(
            await self.session.scalar(
                select(func.count(RequirementItem.id)).where(
                    RequirementItem.requirement_id == requirement_id
                )
            )
            or 0
        )
        confirmed_count = int(
            await self.session.scalar(
                select(func.count(RequirementItem.id)).where(
                    RequirementItem.requirement_id == requirement_id,
                    RequirementItem.confirmed.is_(True),
                )
            )
            or 0
        )
        extraction_status = await self.session.scalar(
            select(RequirementExtractionTask.status)
            .where(RequirementExtractionTask.requirement_id == requirement_id)
            .order_by(RequirementExtractionTask.id.desc())
            .limit(1)
        )
        generation_status = await self.session.scalar(
            select(CaseGenerationTask.status)
            .where(CaseGenerationTask.requirement_id == requirement_id)
            .order_by(CaseGenerationTask.id.desc())
            .limit(1)
        )
        linked_cases = (
            select(distinct(TestCase.id).label("case_id"))
            .join(RequirementCaseLink, RequirementCaseLink.test_case_id == TestCase.id)
            .join(RequirementItem, RequirementItem.id == RequirementCaseLink.requirement_item_id)
            .where(RequirementItem.requirement_id == requirement_id, TestCase.deleted_at.is_(None))
            .subquery()
        )
        review_count = int(
            await self.session.scalar(
                select(func.count(TestCase.id)).where(
                    TestCase.id.in_(select(linked_cases.c.case_id)),
                    TestCase.status.in_(
                        (
                            TestCaseStatus.DRAFT.value,
                            TestCaseStatus.REVIEWING.value,
                            TestCaseStatus.APPROVED.value,
                        )
                    ),
                )
            )
            or 0
        )
        published_count = int(
            await self.session.scalar(
                select(func.count(TestCase.id)).where(
                    TestCase.id.in_(select(linked_cases.c.case_id)),
                    TestCase.status == TestCaseStatus.PUBLISHED.value,
                )
            )
            or 0
        )
        automatable_count = int(
            await self.session.scalar(
                select(func.count(TestCase.id)).where(
                    TestCase.id.in_(select(linked_cases.c.case_id)),
                    TestCase.status == TestCaseStatus.PUBLISHED.value,
                    TestCase.automatable.is_(True),
                )
            )
            or 0
        )
        return {
            "requirement_item_count": item_count,
            "confirmed_item_count": confirmed_count,
            "extraction_status": extraction_status,
            "generation_status": generation_status,
            "review_case_count": review_count,
            "published_case_count": published_count,
            "automatable_published_case_count": automatable_count,
        }
