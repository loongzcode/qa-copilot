from typing import Any

import jwt

from app.core.constants import ErrorCode
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.exceptions.exception_business import ForbiddenException, UnauthorizedException
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.schemas.dto.auth import LoginDTO, RefreshTokenDTO
from app.schemas.vo.auth import LoginVO
from app.schemas.vo.user import UserInfoVO


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self.repository: AuthRepository = repository

    @staticmethod
    def _build_tokens(user_id: int) -> LoginVO:
        subject = str(user_id)
        return LoginVO(
            token=create_access_token(subject),
            refresh_token=create_refresh_token(subject),
        )

    async def login(self, payload: LoginDTO) -> LoginVO:
        user: User | None = await self.repository.get_by_username(
            username=payload.username
        )
        if user is None or not verify_password(
            password=payload.password, hashed_password=user.password_hash
        ):
            raise UnauthorizedException(
                "用户名或密码错误", code=ErrorCode.INVALID_CREDENTIALS
            )

        if not user.is_active:
            raise ForbiddenException("用户已被停用")
        return self._build_tokens(user_id=user.id)

    async def user_info(self, user: User) -> UserInfoVO:
        roles: list[str] = [role.code for role in user.roles if role.enabled]
        if user.is_superuser and "R_SUPER" not in roles:
            roles.append("R_SUPER")
        buttons: set[str] = (
            {"*"}
            if user.is_superuser
            else {
                menu.permission_code
                for role in user.roles
                if role.enabled
                for menu in role.menus
                if menu.enabled and menu.menu_type == "button" and menu.permission_code
            }
        )
        return UserInfoVO(
            user_id=str(user.id),
            user_name=user.display_name or user.username,
            roles=roles,
            buttons=sorted(buttons),
        )

    async def refresh(self, payload: RefreshTokenDTO) -> LoginVO:
        try:
            token_payload: dict[str, Any] = decode_token(
                payload.refresh_token, expected_type="refresh"
            )
            user_id = int(token_payload["sub"])
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            raise UnauthorizedException(
                "刷新令牌无效", code=ErrorCode.REFRESH_TOKEN_INVALID
            ) from exc
        user: User | None = await self.repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedException(
                "用户不存在或已停用", code=ErrorCode.REFRESH_TOKEN_INVALID
            )
        return self._build_tokens(user_id=user.id)
