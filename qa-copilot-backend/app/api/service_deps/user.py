from typing import Annotated

from app.core.deps import DbSession
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService
from fastapi import Depends


def get_user_service(db: DbSession) -> UserService:

    return UserService(UserRepository(session=db))


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
