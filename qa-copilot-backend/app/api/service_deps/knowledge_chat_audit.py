"""知识问答审计依赖。"""

from typing import Annotated

from app.core.deps import DbSession
from app.repositories.knowledge_chat_repository import KnowledgeChatRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.knowledge_chat_audit_service import KnowledgeChatAuditService
from fastapi import Depends


def get_knowledge_chat_audit_service(db: DbSession) -> KnowledgeChatAuditService:
    return KnowledgeChatAuditService(KnowledgeChatRepository(db), TestProjectsRepository(db))


KnowledgeChatAuditServiceDep = Annotated[KnowledgeChatAuditService, Depends(get_knowledge_chat_audit_service)]
