from typing import Annotated

from app.core.deps import DbSession
from app.repositories.route_repository import RouteRepository
from app.services.route_service import RouteService
from fastapi import Depends


def get_route_service(db: DbSession) -> RouteService:

    return RouteService(RouteRepository(session=db))


RouteServiceDep = Annotated[RouteService, Depends(get_route_service)]