from typing import Annotated

from app.core.deps import DbSession
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.knowledge_document_repository import KnowledgeDocumentRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.test_modules_repository import TestModulesRepository
from app.services.knowledge_document_service import KnowledgeDocumentService
from app.storage import get_document_storage
from fastapi import Depends


def get_knowledge_document_service(db: DbSession) -> KnowledgeDocumentService:
    return KnowledgeDocumentService(
        repository = KnowledgeDocumentRepository(session=db),
        outbox_event_repository=OutboxEventRepository(session=db),
        knowledge_base_repository=KnowledgeBaseRepository(session=db),
        test_modules_repository=TestModulesRepository(session=db),
        document_storage=get_document_storage(),
    )

KnowledgeDocumentServiceDep = Annotated[KnowledgeDocumentService, Depends(get_knowledge_document_service)]

