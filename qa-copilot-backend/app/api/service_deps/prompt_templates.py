from typing import Annotated

from app.core.deps import DbSession
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.services.prompt_template_service import PromptTemplateService
from fastapi import Depends


def get_prompt_templates_service(db: DbSession) -> PromptTemplateService:
    return PromptTemplateService(PromptTemplateRepository(session=db))

PromptTemplateServiceDep = Annotated[PromptTemplateService, Depends(get_prompt_templates_service)]

