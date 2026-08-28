"""查询并解释需求到自动化的多 Agent 协作状态。"""

from app.agents.quality_delivery_coordinator import QualityDeliveryFacts, coordinate_quality_delivery
from app.exceptions import NotFoundException
from app.models import User
from app.repositories.quality_delivery_repository import QualityDeliveryRepository
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.vo.quality_delivery import QualityDeliveryStatusVO


class QualityDeliveryService:
    """在项目权限边界内组装持久化事实并调用确定性协调器。"""

    def __init__(
        self,
        repository: QualityDeliveryRepository,
        project_repository: TestProjectsRepository,
        requirement_repository: RequirementsRepository,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.requirement_repository = requirement_repository

    async def get_status(self, project_id: int, requirement_id: int, current_user: User) -> QualityDeliveryStatusVO:
        """返回当前流程阶段，但不会自动越过人工确认或直接发布资产。"""
        if await self.project_repository.get_accessible_project(project_id, current_user) is None:
            raise NotFoundException("项目不存在或无权访问")
        if await self.requirement_repository.get_requirement_detail(project_id, requirement_id) is None:
            raise NotFoundException("需求不存在")
        raw_facts = await self.repository.load_facts(requirement_id)
        facts = QualityDeliveryFacts(**raw_facts)
        decision = coordinate_quality_delivery(facts)
        return QualityDeliveryStatusVO(
            stage=decision.stage,
            current_agent=decision.current_agent,
            next_action=decision.next_action,
            blockers=list(decision.blockers),
            requirement_item_count=facts.requirement_item_count,
            confirmed_item_count=facts.confirmed_item_count,
            review_case_count=facts.review_case_count,
            published_case_count=facts.published_case_count,
            automatable_published_case_count=facts.automatable_published_case_count,
        )
