"""知识问答独立审计只读服务。"""

from app.core.constants import KnowledgeChatMessageRole, KnowledgeChatMessageStatus, KnowledgeChatSessionStatus
from app.exceptions import NotFoundException
from app.models import User
from app.repositories.knowledge_chat_repository import KnowledgeChatRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.api_result import PageResult
from app.schemas.vo.knowledge_chat import (
    KnowledgeChatMessageCursorVO,
    KnowledgeChatMessageVO,
    KnowledgeChatSessionVO,
    KnowledgeCitationVO,
)


class KnowledgeChatAuditService:
    """允许审计员只读检查项目会话，不复用普通用户所有权查询。"""

    def __init__(self, repository: KnowledgeChatRepository, project_repository: TestProjectsRepository) -> None:
        self.repository = repository
        self.project_repository = project_repository

    async def _require_project(self, project_id: int, current_user: User) -> None:
        if await self.project_repository.get_accessible_project(project_id, current_user) is None:
            raise NotFoundException("项目不存在或无权审计")

    @staticmethod
    def _session_vo(item) -> KnowledgeChatSessionVO:
        data = KnowledgeChatSessionVO.model_validate(item, from_attributes=True)
        data.user_name = item.user.username if item.user is not None else None
        return data

    @staticmethod
    def _message_vo(item) -> KnowledgeChatMessageVO:
        return KnowledgeChatMessageVO(
            id=item.id,
            session_id=item.session_id,
            role=KnowledgeChatMessageRole(item.role),
            content=item.content,
            citations=[KnowledgeCitationVO.model_validate(value) for value in item.citations],
            model_id=item.model_id,
            prompt_template_id=item.prompt_template_id,
            status=KnowledgeChatMessageStatus(item.status),
            token_count=item.token_count,
            error_message=item.error_message,
            created_at=item.created_at,
        )

    async def list_sessions(
        self,
        project_id: int,
        current_user: User,
        *,
        knowledge_base_id: int | None,
        user_id: int | None,
        status: KnowledgeChatSessionStatus | None,
        current: int,
        size: int,
    ) -> PageResult[KnowledgeChatSessionVO]:
        await self._require_project(project_id, current_user)
        records, total = await self.repository.list_audit_sessions(
            project_id, knowledge_base_id, user_id, status, current, size
        )
        return PageResult(
            current=current,
            size=size,
            total=total,
            records=[self._session_vo(item) for item in records],
        )

    async def list_messages(
        self,
        project_id: int,
        session_id: int,
        current_user: User,
        before_id: int | None,
        limit: int,
    ) -> KnowledgeChatMessageCursorVO:
        await self._require_project(project_id, current_user)
        if await self.repository.get_project_session(project_id, session_id) is None:
            raise NotFoundException("审计会话不存在")
        messages, has_more = await self.repository.list_messages(session_id, before_id, limit)
        records = [self._message_vo(item) for item in messages]
        return KnowledgeChatMessageCursorVO(
            records=records,
            has_more=has_more,
            next_cursor=records[0].id if has_more and records else None,
        )
