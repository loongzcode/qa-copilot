from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models import Role, User
from app.repositories.user_repository import UserRepository
from app.schemas.dto.user import UserCreateDTO, UserUpdateDTO
from app.schemas.vo.user import UserVO


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository: UserRepository = repository

    @staticmethod
    def _user_read(user: User) -> UserVO:
        return UserVO(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            role_ids=[role.id for role in user.roles],
            role_codes=[role.code for role in user.roles if role.enabled],
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    async def list_users(self, current, size, keyword):
        users, total = await self.repository.list_users(current, size, keyword)
        return [self._user_read(user) for user in users], total

    async def create_user(self, payload: UserCreateDTO) -> UserVO:
        # 得到权限列表
        roles = await self._get_roles(payload.role_ids)
        # 组建用户对象
        user = User(
            username=payload.username,
            display_name=payload.display_name,
            password_hash=hash_password(payload.password),
            is_active=payload.is_active,
            is_superuser=any(role.code == "R_SUPER" for role in roles),
            roles=roles,
        )
        self.repository.add(user)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("用户已存在") from exc
        return self._user_read(user)

    async def _get_roles(self, role_ids: list[int]) -> list[Role]:
        roles = await self.repository.get_roles(role_ids)
        if len(roles) != len(set(role_ids)):
            raise BadRequestException("部分角色不存在")
        return roles

    async def update_user(self, user_id: int, payload: UserUpdateDTO, current_user_id: int) -> UserVO:
        user = await self.repository.get_user(user_id, with_roles=True)
        if user is None:
            raise NotFoundException("用户不存在")
        # 把前端提交的更新参数转换成字典，只保留前端明确传入的字段，同时排除 password 和 role_ids
        changes = payload.model_dump(exclude_unset=True, exclude={"password", "role_ids"})
        if user.id == current_user_id and changes.get("is_active") is False:
            raise BadRequestException("不能停用当前登录账号")
        for key, value in changes.items():
            setattr(user, key, value)
        if payload.password:
            user.password_hash = hash_password(payload.password)
        if payload.role_ids is not None:
            roles = await self._get_roles(payload.role_ids)
            user.roles = roles
            user.is_superuser = any(role.code == "R_SUPER" for role in roles)
        await self.repository.commit()
        return self._user_read(user)

    async def delete_user(self, user_id, current_user):
        user = await self.repository.get_user(user_id, with_roles=True)
        if user is None:
            raise NotFoundException("用户不存在")
        if user.is_superuser:
            raise BadRequestException("不能删除管理员账号")
        if user_id == current_user:
            raise BadRequestException("不能删除当前登录账号")
        await self.repository.delete(user)
        await self.repository.commit()
