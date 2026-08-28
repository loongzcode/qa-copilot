from typing import Annotated

from app.core.deps import DbSession
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.ai_provider_repository import AIProviderRepository
from app.services.ai_model_service import AIModelService
from fastapi import Depends


def get_ai_model_service(db: DbSession) -> AIModelService:
    return AIModelService(AIModelRepository(db),AIProviderRepository(db))


AIModelServiceDep = Annotated[AIModelService, Depends(get_ai_model_service)]
