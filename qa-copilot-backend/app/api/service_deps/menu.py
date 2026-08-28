from typing import Annotated

from app.core.deps import DbSession
from app.repositories.menu_repository import MenuRepository
from app.services.menu_service import MenuService
from fastapi import Depends


def get_menu_service(db: DbSession) -> MenuService:
    return MenuService(MenuRepository(session=db))

MenuServiceDep = Annotated[MenuService, Depends(get_menu_service)]

