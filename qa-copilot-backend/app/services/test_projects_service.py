from sqlalchemy.exc import IntegrityError

from app.core.constants import ProjectMemberRole, ProjectStatus
from app.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.models import TestProjectMember, User
from app.models.test_projects import TestProjects
from app.repositories.test_project_members_repository import TestProjectMembersRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.repositories.user_repository import UserRepository
from app.schemas.dto.test_projects import TestProjectCreateDTO, TestProjectUpdateDTO
from app.schemas.vo.test_projects import TestProjectVO


def _violates_constraint(exc: IntegrityError, constraint_name: str) -> bool:
    """判断一次数据库完整性异常是否来自指定约束。

    功能：沿异常链读取 PostgreSQL/asyncpg 提供的 constraint_name；部分驱动
    没有暴露结构化字段时，再使用异常文本作兼容判断。
    作用：Service 只有确认命中项目编码唯一约束时，才向前端返回“项目已存在”。
    为什么用它：IntegrityError 还可能来自外键、非空和检查约束，不能把所有
    完整性错误都解释成编码重复；保留未知原异常更利于日志定位真实原因。
    """

    # SQLAlchemy 将数据库驱动异常保存在 orig 中；约束名称通常也位于 orig
    # 或它的 __cause__ 链上，因此从原始驱动异常开始检查。
    current: BaseException | None = exc.orig
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if getattr(current, "constraint_name", None) == constraint_name:
            return True
        diagnostic = getattr(current, "diag", None)
        if getattr(diagnostic, "constraint_name", None) == constraint_name:
            return True
        current = current.__cause__ or current.__context__

    return constraint_name in str(exc.orig)


class TestProjectsService:
    def __init__(
        self,
        repository: TestProjectsRepository,
        user_repository: UserRepository,
        member_repository: TestProjectMembersRepository,
    ):
        self.repository = repository
        self.user_repository = user_repository
        self.member_repository = member_repository

    @staticmethod
    def _test_project_read(project: TestProjects) -> TestProjectVO:
        return TestProjectVO(
            id=project.id,
            name=project.name,
            description=project.description,
            code=project.code,
            owner_id=project.owner_id,
            owner_name=project.owner.display_name if project.owner else None,
            member_count=project.member_count,
            module_count=project.module_count,
            status=ProjectStatus(project.status),
            updated_at=project.updated_at,
        )

    async def list_projects(
        self,
        current_user: User,
        current: int,
        size: int,
        keyword: str,
        status: ProjectStatus | None,
    ):
        projects, total = await self.repository.list_projects(current_user, current, size, keyword, status)
        return [self._test_project_read(project) for project in projects], total

    async def create_project(self, payload: TestProjectCreateDTO, current_user: User):
        # 超级管理员传了 owner_id，就使用管理员选择的负责人。
        if current_user.is_superuser and payload.owner_id is not None:
            owner_id = payload.owner_id
        else:
            # 普通用户不能替别人创建项目，负责人强制设为自己。
            # 超级管理员没选择负责人时，也默认设为自己。
            owner_id = current_user.id
        owner = await self.user_repository.get_user(owner_id)
        if owner is None or not owner.is_active:
            raise BadRequestException("负责人不存在或已停用")

        test_projects = TestProjects(
            name=payload.name,
            description=payload.description,
            code=payload.code,
            owner_id=owner_id,
            owner=owner,
            member_count=1,
            module_count=0,
        )
        self.repository.add(test_projects)
        try:
            # 先执行项目 INSERT，获得数据库生成的 project.id，但暂不提交事务。
            await self.repository.flush()
            owner_member = TestProjectMember(
                project_id=test_projects.id,
                user_id=owner.id,
                member_role=ProjectMemberRole.OWNER.value,
                project=test_projects,
                user=owner,
            )
            self.repository.add(owner_member)
            await self.repository.commit()
        except IntegrityError as e:
            await self.repository.rollback()
            if _violates_constraint(e, "uq_test_projects_code"):
                raise ConflictException("项目编码已存在") from e
            # 不是已知的项目编码冲突时保留原异常，让统一异常日志记录真实约束。
            raise
        return self._test_project_read(test_projects)

    async def update_project(self, project_id: int, payload: TestProjectUpdateDTO, current_user: User):
        project = await self.repository.get_accessible_project(project_id, current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        if project.status == ProjectStatus.ARCHIVED:
            raise BadRequestException("已归档项目不能编辑")
        # owner_id 单独处理，不能直接跟普通字段一起 setattr。
        changes = payload.model_dump(exclude_unset=True, exclude={"owner_id"})
        for key, value in changes.items():
            setattr(project, key, value)
        old_owner_id = project.owner_id
        owner_id = payload.owner_id
        if owner_id is not None:
            if not current_user.is_superuser:
                if owner_id != project.owner_id:
                    raise ForbiddenException("普通用户不能更换项目负责人")
            else:
                owner = await self.user_repository.get_user(owner_id)
                if owner is None or not owner.is_active:
                    raise BadRequestException("负责人不存在或已停用")
                if owner.id != old_owner_id:
                    new_owner_member = await self.member_repository.get_member(
                        project_id,owner.id
                    )
                    if new_owner_member is None:
                        new_owner_member = TestProjectMember(
                            project_id=project.id,
                            user_id=owner.id,
                            member_role=ProjectMemberRole.OWNER.value,
                            project=project,
                            user=owner,
                        )
                        self.member_repository.add(new_owner_member)
                    else:
                        new_owner_member.member_role = ProjectMemberRole.OWNER.value
                    if old_owner_id is not None:
                        old_owner_member = await self.member_repository.get_member(
                            project.id,
                            old_owner_id,
                        )
                        if old_owner_member is not None:
                            old_owner_member.member_role = ProjectMemberRole.MEMBER.value
                project.owner_id = owner.id
                project.owner = owner
        try:
            await self.repository.commit()
        except IntegrityError:
            await self.repository.rollback()
            # 编辑接口不修改项目编码，未知完整性错误不能伪装成“项目已存在”。
            raise
        updated_project = await self.repository.get_accessible_project(
            project_id,
            current_user,
        )

        if updated_project is None:
            raise NotFoundException("项目不存在或无权操作")
        return self._test_project_read(updated_project)

    async def archive_project(self, project_id: int, current_user: User):
        project = await self.repository.get_accessible_project(project_id, current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        if project.status == ProjectStatus.ARCHIVED:
            raise BadRequestException("项目已经归档")
        if project.status != ProjectStatus.ACTIVE:
            raise BadRequestException("当前项目状态不能归档")
        project.status = ProjectStatus.ARCHIVED.value
        try:
            await self.repository.commit()
        except IntegrityError:
            await self.repository.rollback()
            # 状态更新理论上不会产生编码冲突，保留原异常用于定位真实约束。
            raise
        archived_project = await self.repository.get_accessible_project(project_id, current_user)
        if archived_project is None:
            raise NotFoundException("项目不存在或无权操作")

        return self._test_project_read(archived_project)

    async def start_project(self, project_id, current_user):
        project = await self.repository.get_accessible_project(project_id, current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        if project.status != ProjectStatus.DRAFT:
            raise BadRequestException("只有未开始的项目可以启动")
        project.status = ProjectStatus.ACTIVE.value
        try:
            await self.repository.commit()
        except IntegrityError:
            await self.repository.rollback()
            # 数据库完整性错误不等于重复启动；重复启动已由上方状态判断处理。
            raise
        started_project = await self.repository.get_accessible_project(
            project_id,
            current_user,
        )
        if started_project is None:
            raise NotFoundException("项目不存在或无权操作")

        return self._test_project_read(started_project)
