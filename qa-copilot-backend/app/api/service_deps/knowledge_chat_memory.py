from typing import Annotated

from app.core.deps import DbSession
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_chat_repository import KnowledgeChatRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.services.knowledge_chat_memory_service import (
    KnowledgeChatMemoryService,
)
from fastapi import Depends


def get_knowledge_chat_memory_service(
        db: DbSession,
) -> KnowledgeChatMemoryService:
    """创建知识问答记忆 Service，并注入同一个请求级数据库 Session。"""

    return KnowledgeChatMemoryService(
        knowledge_chat_repository=KnowledgeChatRepository(session=db),
        ai_model_repository=AIModelRepository(session=db),
        prompt_template_repository=PromptTemplateRepository(session=db),
    )


KnowledgeChatMemoryServiceDep = Annotated[
    KnowledgeChatMemoryService,
    Depends(get_knowledge_chat_memory_service),
]