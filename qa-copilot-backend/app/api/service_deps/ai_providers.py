from typing import Annotated

from app.core.deps import DbSession
from app.repositories.ai_provider_repository import AIProviderRepository
from app.services.ai_provider_service import AiProviderService
from fastapi import Depends


def get_ai_providers_service(db: DbSession) -> AiProviderService:
    return AiProviderService(AIProviderRepository(db))


AiProviderServiceDep = Annotated[AiProviderService,Depends(get_ai_providers_service)]