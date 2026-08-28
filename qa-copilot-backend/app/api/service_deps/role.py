from typing import Annotated

from app.core.deps import DbSession
from app.repositories.role_repository import RoleRepository
from app.services.role_service import RoleService
from fastapi import Depends


def get_role_service(db: DbSession) -> RoleService:

    return RoleService(RoleRepository(session=db))


RoleServiceDep = Annotated[RoleService, Depends(get_role_service)]