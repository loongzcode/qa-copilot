from typing import Annotated

from app.core.deps import DbSession
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.knowledge_base_service import KnowledgeBaseService
from fastapi import Depends


def get_knowledge_base_service(db: DbSession) -> KnowledgeBaseService:
    return KnowledgeBaseService(
        repository=KnowledgeBaseRepository(session=db),
        project_repository=TestProjectsRepository(session=db),
        model_repository= AIModelRepository(session=db),
    )

KnowledgeBaseServiceDep = Annotated[KnowledgeBaseService, Depends(get_knowledge_base_service)]

