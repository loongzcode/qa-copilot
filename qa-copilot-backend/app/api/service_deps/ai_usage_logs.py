"""组装 AI 调用日志 Service 所需依赖。"""
from typing import Annotated

from app.core.deps import DbSession
from app.repositories.ai_usage_logs_repository import AIUsageLogsRepository
from app.services.ai_usage_logs_service import AIUsageLogsService
from fastapi import Depends


def get_ai_usage_logs_service(db: DbSession) -> AIUsageLogsService:

    return AIUsageLogsService(AIUsageLogsRepository(session=db))


AIUsageLogsServiceDep = Annotated[AIUsageLogsService, Depends(get_ai_usage_logs_service)]