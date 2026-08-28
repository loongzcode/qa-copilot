from typing import Annotated

from app.core.deps import DbSession
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.knowledge_search_repository import KnowledgeSearchRepository
from app.services.knowledge_search_service import KnowledgeSearchService
from fastapi import Depends


def get_knowledge_search_service(db: DbSession) -> KnowledgeSearchService:
    """为一次请求创建知识检索 Service 及其数据库依赖。

    三个 Repository 共享 FastAPI 为当前请求提供的同一个 AsyncSession：
    KnowledgeBaseRepository 负责数据权限，AIModelRepository 负责模型与用量，
    KnowledgeSearchRepository 负责向量和全文检索 SQL。
    """

    return KnowledgeSearchService(
        knowledge_base_repository=KnowledgeBaseRepository(session=db),
        ai_model_repository=AIModelRepository(session=db),
        search_repository=KnowledgeSearchRepository(session=db),
    )


KnowledgeSearchServiceDep = Annotated[
    KnowledgeSearchService,
    # 路由声明这个类型后，FastAPI 会调用上面的工厂函数完成依赖注入。
    Depends(get_knowledge_search_service),
]
