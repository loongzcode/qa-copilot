"""组装 Supervisor Service 的请求级依赖。"""

from typing import Annotated

from app.core.deps import DbSession
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.repositories.supervisor_repository import SupervisorRepository
from app.repositories.test_project_members_repository import TestProjectMembersRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.services.supervisor_service import SupervisorService
from fastapi import Depends


def get_supervisor_service(db: DbSession) -> SupervisorService:
    """让规划、AI 日志、项目权限和持久化 Repository 共用当前请求事务 Session。"""
    return SupervisorService(
        repository=SupervisorRepository(db),
        project_repository=TestProjectsRepository(db),
        project_member_repository=TestProjectMembersRepository(db),
        ai_model_repository=AIModelRepository(db),
        prompt_template_repository=PromptTemplateRepository(db),
        outbox_repository=OutboxEventRepository(db),
    )


SupervisorServiceDep = Annotated[SupervisorService, Depends(get_supervisor_service)]
