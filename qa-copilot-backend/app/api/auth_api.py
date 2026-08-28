from fastapi import APIRouter

from app.api.service_deps.auth import AuthServiceDep
from app.core.deps import CurrentUser
from app.schemas.api_result import ApiResult, success
from app.schemas.dto.auth import LoginDTO, RefreshTokenDTO
from app.schemas.vo.auth import LoginVO
from app.schemas.vo.user import UserInfoVO

router = APIRouter(prefix="/auth",tags=["登录"])


# 登录
@router.post("/login", response_model=ApiResult[LoginVO],summary="登录") 
async def login(payload: LoginDTO,service: AuthServiceDep) -> ApiResult[LoginVO]:
    return success(await service.login(payload),'登录成功')

# 获取用户信息
@router.get("/getUserInfo", response_model=ApiResult[UserInfoVO])
async def get_user_info(current_user: CurrentUser, service: AuthServiceDep) -> ApiResult[UserInfoVO]:
    return success(await service.user_info(current_user))


@router.post("/refreshToken", response_model=ApiResult[LoginVO])
async def refresh_token(
    payload: RefreshTokenDTO, service: AuthServiceDep
) -> ApiResult[LoginVO]:
    return success(await service.refresh(payload), "令牌刷新成功")
