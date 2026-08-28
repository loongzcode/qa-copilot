"""多 Agent 质量交付协调状态响应。"""

from app.agents.quality_delivery_coordinator import QualityDeliveryStage
from app.schemas.camel_model import CamelModel


class QualityDeliveryStatusVO(CamelModel):
    """告诉页面流程停在哪、由谁处理、下一步做什么。"""

    stage: QualityDeliveryStage
    current_agent: str | None
    next_action: str
    blockers: list[str]
    requirement_item_count: int
    confirmed_item_count: int
    review_case_count: int
    published_case_count: int
    automatable_published_case_count: int
