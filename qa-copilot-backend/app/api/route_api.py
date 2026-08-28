from typing import Annotated

from fastapi import APIRouter, Query

from app.api.service_deps.route import RouteServiceDep
from app.core.deps import CurrentUser
from app.schemas.api_result import ApiResult, success

router = APIRouter(prefix="/route", tags=["动态路由"])


@router.get("/getConstantRoutes", response_model=ApiResult[list[dict]])
async def get_constant_routes() -> ApiResult[list[dict]]:
    """常量路由不依赖登录状态，令牌失效后仍然可以显示登录页。"""

    return success(
        [
            {
                "id": "login",
                "name": "login",
                "path": "/login",
                "component": "layout.blank$view.login",
                "meta": {"title": "登录", "constant": True, "hideInMenu": True},
            },
            *[
                {
                    "id": code,
                    "name": code,
                    "path": f"/{code}",
                    "component": f"layout.blank$view.{code}",
                    "meta": {"title": code, "constant": True, "hideInMenu": True},
                }
                for code in ("403", "404", "500")
            ],
        ]
    )

@router.get("/getUserRoutes", response_model=ApiResult[dict])
async def get_user_routes(current_user: CurrentUser, service: RouteServiceDep) -> ApiResult[dict]:
    routes = await service.user_routes(current_user)
    return success(routes)


@router.get("/isRouteExist", response_model=ApiResult[bool])
async def is_route_exist(
    route_name: Annotated[str, Query(alias="routeName")],
    current_user: CurrentUser,
    service: RouteServiceDep,
) -> ApiResult[bool]:
    return success(await service.route_exists(current_user, route_name))
