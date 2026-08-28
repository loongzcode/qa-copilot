"""FastAPI 的数据库、身份认证和权限依赖。

这里的 ``deps`` 是 dependencies（依赖）的缩写。文件名本身没有特殊作用，
真正触发 FastAPI 依赖注入的是 ``Depends(...)``。
"""

from collections.abc import Callable
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models import User
from app.repositories.auth_repository import AuthRepository

# ``Annotated[T, Depends(provider)]`` 同时表达两件事：
# 1. 交给编辑器/类型检查器看的参数类型是 T；
# 2. 运行时由 FastAPI 调用 provider，并把结果注入这个参数。
#
# 因此函数参数声明 ``db: DbSession`` 时，FastAPI 会先调用 get_db()，把它
# yield 出来的 AsyncSession 赋给 db。单次请求内多处依赖 get_db() 时，
# FastAPI 默认复用同一个依赖结果，让多个 Repository 共享同一个 Session。


type DbSession = Annotated[AsyncSession, Depends(get_db)]


# 从 ``Authorization: Bearer <token>`` 请求头中读取凭证。
# auto_error=False 表示没有令牌时返回 None，由 get_current_user 统一生成
# 项目约定格式的 401 响应，而不是让 HTTPBearer 提前抛出自己的错误。
bearer_scheme = HTTPBearer(auto_error=False)


# 得到用户并进行权限判断
async def get_current_user(
    db: DbSession,
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(dependency=bearer_scheme)
    ],
) -> User:
    """解析访问令牌，并返回数据库中当前仍然有效的用户。

    参数说明：
    - ``db``：由 ``get_db()`` 注入的 AsyncSession。
    - ``credentials``：由 ``bearer_scheme`` 从 Bearer 请求头解析出的令牌。

    即使 JWT 本身有效，也重新查询数据库，以确认用户仍存在且未被停用。
    查询时加载角色和菜单，后续权限检查便可以直接读取 ``user.roles``。
    """
    # 没有 Authorization: Bearer 请求头时，credentials 为 None。
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="请先登录")
    try:
        # credentials.credentials 是去掉 ``Bearer `` 前缀后的 JWT 字符串。
        # access 表示这里只接受访问令牌，不接受刷新令牌。
        payload: dict[str, Any] = decode_token(credentials.credentials, "access")
        # JWT 的 sub 字段保存用户 ID；数据库主键是 int，因此在这里转换。
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态已失效",
        ) from exc
    # Repository 不会自己创建数据库连接，而是接收上面注入的同一个 db。
    # AuthRepository(db) 最终会在 BaseRepository 中保存 self.session = db。
    user = await AuthRepository(db).get_by_id(user_id, with_permissions=True)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已停用",
        )
    # 仅保存主键供请求完成日志关联用户，不记录令牌、密码或请求正文。
    request.state.user_id = user.id
    return user


# 接口声明 ``current_user: CurrentUser`` 时，FastAPI 会先完成令牌解析和
# 数据库查询，再把返回的 User 对象传入 current_user 参数。
# 使用依赖依赖，方便其他接口使用
CurrentUser = Annotated[User, Depends(get_current_user)]


# 判断用户是否有权限
async def require_superuser(current_user: CurrentUser) -> User:
    """要求当前用户是超级管理员，否则返回 403。

    ``current_user: CurrentUser`` 是一个子依赖：FastAPI 会先执行
    get_current_user()，只有登录状态有效时才继续执行本函数。
    """

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要超级管理员权限",
        )
    return current_user


# 接口声明 ``user: SuperUser`` 后，FastAPI 会自动依次执行：
# get_db -> get_current_user -> require_superuser -> 接口函数。
# 得到管理员账号
SuperUser = Annotated[User, Depends(require_superuser)]


def get_permission_codes(user: User) -> set[str | None] | set[str]:
    """汇总用户通过所有启用角色获得的按钮权限码。

    超级管理员返回通配符 ``{"*"}``；普通用户只收集已启用角色下、已启用且
    类型为 button 的菜单权限码。使用 set 可以自动去掉重复权限。
    """
    if user.is_superuser:
        return {"*"}
    return {
        menu.permission_code
        for role in user.roles
        if role.enabled
        for menu in role.menus
        if menu.enabled and menu.menu_type == "button" and menu.permission_code
    }


def require_permission(code: str) -> Callable:
    """根据权限码创建一个可复用的 FastAPI 权限依赖。

    ``code`` 是接口要求的权限，例如 ``system:user:add``。本函数不会立即检查
    用户，而是返回内部的 ``checker`` 函数；FastAPI 收到请求时才调用它。

    使用示例：
    ``user: Annotated[User, Depends(require_permission("system:user:add"))]``
    """

    async def checker(current_user: CurrentUser) -> User:
        permissions: set[str | None] | set[str] = get_permission_codes(current_user)
        if "*" not in permissions and code not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少操作权限：{code}",
            )
        # 返回用户对象后，接口还可以继续读取当前用户信息。
        return current_user

    return checker


def get_request_id(request: Request) -> str:
    """读取 RequestIdMiddleware 为当前请求生成的链路编号。"""

    return request.state.request_id

# API 参数声明 request_id: RequestId 时，
# FastAPI 会调用 get_request_id() 并注入当前请求的链路编号。
RequestId = Annotated[str, Depends(get_request_id)]
