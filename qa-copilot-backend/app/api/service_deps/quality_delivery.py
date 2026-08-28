"""多 Agent 质量交付协调服务依赖。"""

from typing import Annotated

from app.core.deps import DbSession
from app.repositories.quality_delivery_repository import QualityDeliveryRepository
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.quality_delivery_service import QualityDeliveryService
from fastapi import Depends


def get_quality_delivery_service(db: DbSession) -> QualityDeliveryService:
    """让三个 Repository 共用当前请求的同一个只读数据库会话。"""
    return QualityDeliveryService(
        QualityDeliveryRepository(db),
        TestProjectsRepository(db),
        RequirementsRepository(db),
    )


QualityDeliveryServiceDep = Annotated[QualityDeliveryService, Depends(get_quality_delivery_service)]
