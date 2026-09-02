"""智能数据查询 Service 的 FastAPI 依赖装配。"""

from typing import Annotated

from app.core.deps import DbSession
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.data_query_repository import DataQueryRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.data_query_service import DataQueryService
from fastapi import Depends


def get_data_query_service(db: DbSession) -> DataQueryService:
    """让同一请求中的业务仓储共享同一个异步数据库会话。"""
    return DataQueryService(
        repository=DataQueryRepository(session=db),
        project_repository=TestProjectsRepository(session=db),
        ai_model_repository=AIModelRepository(session=db),
        prompt_template_repository=PromptTemplateRepository(session=db),
    )


DataQueryServiceDep = Annotated[DataQueryService, Depends(get_data_query_service)]
