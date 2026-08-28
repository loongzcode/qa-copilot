
from app.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models import Role
from app.repositories.role_repository import RoleRepository
from app.schemas.dto.role import RoleUpdateDTO
from app.schemas.vo.role import RoleVO


class RoleService:
    def __init__(self, repository: RoleRepository) -> None:
        self.repository: RoleRepository = repository

    @staticmethod
    def _role_read(role: Role) -> RoleVO:
        return RoleVO(
            id=role.id,
            code=role.code,
            name=role.name,
            description=role.description,
            enabled=role.enabled,
            is_system=role.is_system,
            menu_ids=[menu.id for menu in role.menus],
            created_at=role.created_at,
            updated_at=role.updated_at,
        )

    async def get_options(self):
        return await self.repository.get_options()

    async def list_roles(self):
        return [self._role_read(role) for role in await self.repository.list_roles()]

    async def create_role(self, payload):
        role = Role(
            code=payload.code,
            name=payload.name,
            description=payload.description,
            enabled=payload.enabled,
            menus=await self._get_menus(payload.menu_ids),
        )
        self.repository.add(role)
        try:
            await self.repository.commit()
        except NotFoundException as e:
            await self.repository.rollback()
            raise ConflictException("菜单已存在") from e
        return self._role_read(role)

    async def update_role(self, role_id: int, payload: RoleUpdateDTO):
        role = await self.repository.get_role(role_id, with_menus=True)
        if role is None:
            raise NotFoundException("角色不存在")
        changes = payload.model_dump(exclude_unset=True, exclude={"menu_ids"})
        for key, value in changes.items():
            setattr(role, key, value)
        if payload.menu_ids is not None:
            role.menus = await self._get_menus(payload.menu_ids)
        try:
            await self.repository.commit()
        except NotFoundException as e:
            await self.repository.rollback()
            raise ConflictException("菜单已经存在") from e
        return self._role_read(role)

    async def delete_role(self, role_id):
        role  = await self.repository.get_role(role_id)
        if role is None:
            raise NotFoundException("角色不存在")
        if role.is_system:
            raise BadRequestException("系统内置角色不能删除")
        await self.repository.delete(role)
        await self.repository.commit()

    async def _get_menus(self, menu_ids):
        menus = await self.repository.get_menus(menu_ids)
        if len(menus) != len(set(menu_ids)):
            raise BadRequestException("部分菜单或按钮权限不存在")
        return menus
