from typing import Annotated

from app.core.deps import DbSession
from app.repositories.auth_repository import AuthRepository
from app.services.auth_service import AuthService
from fastapi import Depends


def get_auth_service(db: DbSession) -> AuthService:

    return AuthService(AuthRepository(session=db))


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)] 