from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.core.constants import KnowledgeVisibility, ProjectMemberRole
from app.models import KnowledgeBase, TestProjectMember, TestProjects, User
from app.repositories.base_repository import BaseRepository


class KnowledgeBaseRepository(BaseRepository):
    @staticmethod
    def _build_visibility_condition(
        project_id: int,
        current_user: User,
    ) -> ColumnElement[bool]:
        """构造知识库数据权限条件，供列表、详情和检索统一复用。

        exists() 只生成 SQL 子查询；必须把它放进最终条件树并追加到 where()，
        身份判断才会真正参与数据库过滤。
        """

        is_project_owner = exists().where(
            TestProjects.id == project_id,
            TestProjects.owner_id == current_user.id,
        )
        is_project_manager = exists().where(
            TestProjectMember.project_id == project_id,
            TestProjectMember.user_id == current_user.id,
            TestProjectMember.member_role.in_(
                [
                    ProjectMemberRole.OWNER.value,
                    ProjectMemberRole.MANAGER.value,
                ]
            ),
        )
        is_project_member = exists().where(
            TestProjectMember.project_id == project_id,
            TestProjectMember.user_id == current_user.id,
        )

        # 三种范围满足任意一种即可，所以最外层使用 or_；
        # 每个分支要求“范围匹配并且身份匹配”，所以分支内部使用 and_。
        return or_(
            # PROJECT：项目负责人或任意项目成员。
            and_(
                KnowledgeBase.visibility == KnowledgeVisibility.PROJECT.value,
                or_(is_project_owner, is_project_member),
            ),
            # MANAGERS：项目负责人或项目管理员。
            and_(
                KnowledgeBase.visibility == KnowledgeVisibility.MANAGERS.value,
                or_(is_project_owner, is_project_manager),
            ),
            # PRIVATE：仅知识库创建人。
            and_(
                KnowledgeBase.visibility == KnowledgeVisibility.PRIVATE.value,
                KnowledgeBase.created_by == current_user.id,
            ),
        )

    async def list_knowledge_bases(
            self,
            project_id: int,
            current_user: User,
            keyword: str,
            enabled: bool | None,
            current: int,
            size: int,
    ) -> tuple[list[KnowledgeBase], int]:
        conditions = [
            KnowledgeBase.project_id == project_id,
        ]
        if keyword:
            conditions.append(
                or_(
                    KnowledgeBase.name.contains(keyword),
                    KnowledgeBase.description.contains(keyword),
                )
            )
        if enabled is not None:
            conditions.append(
                KnowledgeBase.enabled == enabled
            )
        if not current_user.is_superuser:
            conditions.append(
                self._build_visibility_condition(project_id, current_user)
            )
        total = await self.session.scalar(select(func.count(KnowledgeBase.id)).where(*conditions)) or 0
        knowledge_base_query = (
            select(KnowledgeBase)
            .where(*conditions)
            .options(
        selectinload(KnowledgeBase.embedding_model),
                selectinload(KnowledgeBase.rerank_model),
                selectinload(KnowledgeBase.creator),
            )
            .order_by(KnowledgeBase.updated_at.desc(), KnowledgeBase.id.desc())
            .offset((current - 1) * size)
            .limit(size))
        result = list((await self.session.scalars(knowledge_base_query)).all())
        return result, total



    async def get_by_name(
            self,
            project_id: int,
            name: str,
            exclude_id: int | None = None,
    ) -> KnowledgeBase | None:
        statement = select(KnowledgeBase).where(
            KnowledgeBase.project_id == project_id,
            KnowledgeBase.name == name,
        )
        if exclude_id is not None:
            statement = statement.where(KnowledgeBase.id != exclude_id)
        knowledge_base = await self.session.scalar(statement)
        return knowledge_base

    async def get_accessible_knowledge_base(
            self,
            project_id: int,
            knowledge_base_id: int,
            current_user: User,
    ) -> KnowledgeBase | None:
        conditions = [
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.project_id == project_id,
        ]
        if not current_user.is_superuser:
            conditions.append(
                self._build_visibility_condition(project_id, current_user)
            )

        return  await self.session.scalar(select(KnowledgeBase).options(
                selectinload(KnowledgeBase.embedding_model),
                selectinload(KnowledgeBase.rerank_model),
                selectinload(KnowledgeBase.creator),
            ).where(*conditions))
