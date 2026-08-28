from sqlalchemy.exc import IntegrityError

from app.core.constants import ProjectMemberRole, ProjectStatus
from app.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models import User
from app.models.test_project_members import TestProjectMember
from app.repositories.test_project_members_repository import (
    TestProjectMembersRepository,
)
from app.repositories.test_projects_repository import TestProjectsRepository
from app.repositories.user_repository import UserRepository
from app.schemas.dto.test_project_member import TestProjectMemberCreateDTO
from app.schemas.vo.test_project_member import TestProjectMemberOptionVO, TestProjectMemberVO


class TestProjectMembersService:
    def __init__(
        self,
        repository: TestProjectMembersRepository,
        project_repository: TestProjectsRepository,
        user_repository: UserRepository,
    ):
        self.repository = repository
        self.project_repository = project_repository
        self.user_repository = user_repository

    # 组装响应
    @staticmethod
    def _test_project_member_read(
        member: TestProjectMember,
    ) -> TestProjectMemberVO:
        return TestProjectMemberVO(
            project_id=member.project_id,
            user_id=member.user_id,
            username=member.user.username,
            display_name=member.user.display_name,
            member_role=ProjectMemberRole(member.member_role),
            created_at=member.created_at,
        )

    # 候选用户转换方法
    @staticmethod
    def _member_option_read(user: User) -> TestProjectMemberOptionVO:
        return TestProjectMemberOptionVO(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
        )

    #  查询列表
    async def list_members(self, project_id: int, current_user: User, current: int, size: int, keyword: str):
        project = await self.project_repository.get_accessible_project(project_id, current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权访问")

        members, total = await self.repository.list_members(project_id, current, size, keyword)
        return [self._test_project_member_read(member) for member in members], total

    # 增加项目成员
    async def create_member(self, project_id: int, current_user: User, payload: TestProjectMemberCreateDTO):
        project = await self.project_repository.get_accessible_project(project_id, current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不能管理成员")
        user = await self.user_repository.get_user(payload.user_id)
        if user is None or not user.is_active:
            raise BadRequestException("用户不存在或已停用")
        existing_member = await self.repository.get_member(project_id, payload.user_id)
        if existing_member is not None:
            raise ConflictException("该用户已经是项目成员")
        if payload.member_role == ProjectMemberRole.OWNER and payload.user_id != project.owner_id:
            raise BadRequestException("只有项目负责人可以设置为 OWNER")
        member_role = ProjectMemberRole.OWNER if payload.user_id == project.owner_id else payload.member_role
        member = TestProjectMember(
            project_id=project_id,
            user_id=user.id,
            member_role=member_role.value,
            user=user,
            project=project,
        )
        self.repository.add(member)
        try:
            await self.repository.commit()
        except IntegrityError as e:
            await self.repository.rollback()
            raise ConflictException("该用户已经是项目成员") from e
        return self._test_project_member_read(member)

    async def update_member(self, project_id, user_id, payload, current_user):
        project = await self.project_repository.get_accessible_project(project_id, current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不能管理成员")
        member = await self.repository.get_member(project_id, user_id)
        if member is None:
            raise NotFoundException("项目成员不存在")
        if user_id == project.owner_id and payload.member_role != ProjectMemberRole.OWNER:
            raise BadRequestException("项目负责人必须保持 OWNER 角色")
        if user_id != project.owner_id and payload.member_role == ProjectMemberRole.OWNER:
            raise BadRequestException("不能将普通成员设置未 OWNER")
        member.member_role = payload.member_role.value
        await self.repository.commit()
        return self._test_project_member_read(member)

    async def remove_member(self, project_id, user_id, current_user):
        # 1. 根据 project_id 和 current_user 查询当前用户有权操作的项目。
        #    继续复用 get_accessible_project()，不要只根据项目 ID 直接删除成员。
        project = await self.project_repository.get_accessible_project(project_id, current_user)
        # 2. 如果项目不存在，或者当前用户无权操作，抛出 NotFoundException。
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不能管理成员")
        # 3. 根据 project_id 和 user_id 查询准备移除的项目成员。
        member = await self.repository.get_member(project_id, user_id)
        # 4. 如果成员不存在，抛出 NotFoundException。
        if member is None:
            raise NotFoundException("项目成员不存在")
        # 5. 判断 user_id 是否等于 project.owner_id。
        #    项目负责人不能从成员列表中移除，否则项目会失去 OWNER 成员。
        if user_id == project.owner_id:
            raise BadRequestException("项目负责人不能从成员列表中移除")

        # 6. 调用 Repository 的 delete() 删除成员实体。delete() 是异步方法，需要 await。
        await self.repository.delete(member)
        # 7. 调用 Repository 的 commit() 提交事务，使删除真正写入数据库。
        try:
            await self.repository.commit()
        except IntegrityError as e:
            await self.repository.rollback()
            raise ConflictException("删除出错") from e

    async def list_member_options(self, project_id, current_user, keyword, limit):
        project = await self.project_repository.get_accessible_project(project_id, current_user)
        if  project is None:
            raise NotFoundException("项目不存在或无权操作")
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不能管理成员")
        users = await self.repository.list_member_options(
            project_id,
            keyword,
            limit,
        )
        return [
            self._member_option_read(user)
            for user in users
        ]
