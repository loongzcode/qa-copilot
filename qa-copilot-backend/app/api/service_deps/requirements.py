from typing import Annotated

from app.core.deps import DbSession
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.knowledge_document_repository import KnowledgeDocumentRepository
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.test_modules_repository import TestModulesRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.requirements_service import RequirementsService
from fastapi import Depends


def get_requirements_service(db: DbSession) -> RequirementsService:
    """使用同一个请求级 AsyncSession 组装需求模块需要的依赖。"""

    return RequirementsService(
        repository=RequirementsRepository(session=db),
        test_project_repository=TestProjectsRepository(session=db),
        test_module_repository=TestModulesRepository(session=db),
        knowledge_base_repository=KnowledgeBaseRepository(session=db),
        knowledge_document_repository=KnowledgeDocumentRepository(session=db),
    )


RequirementsServiceDep = Annotated[
    RequirementsService,
    Depends(get_requirements_service),
]
