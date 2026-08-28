from typing import Annotated

from app.api.service_deps.knowledge_chat_memory import KnowledgeChatMemoryServiceDep
from app.api.service_deps.knowledge_search import KnowledgeSearchServiceDep
from app.core.deps import DbSession
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.knowledge_chat_repository import KnowledgeChatRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.services.knowledge_chat_service import KnowledgeChatService
from fastapi import Depends


def get_knowledge_chat_service(
        db: DbSession,
        search_service: KnowledgeSearchServiceDep,
        memory_service:  KnowledgeChatMemoryServiceDep,
) -> KnowledgeChatService:
    """创建知识问答 Service，并注入可复用的知识检索 Service。"""

    return KnowledgeChatService(
        search_service=search_service,
        memory_service=memory_service,
        ai_model_repository=AIModelRepository(session=db),
        prompt_template_repository=PromptTemplateRepository(session=db),
        repository=KnowledgeChatRepository(session=db),
        knowledge_base_repository=KnowledgeBaseRepository(session=db),
    )

KnowledgeChatServiceDep = Annotated[
        KnowledgeChatService,
        Depends(get_knowledge_chat_service),
    ]
