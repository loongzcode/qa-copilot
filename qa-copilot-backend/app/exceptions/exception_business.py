from typing import Any

from app.core.constants import ErrorCode
from app.exceptions.exception_base import BusinessException


class BadRequestException(BusinessException):
    """请求内容合法，但不满足当前业务规则。"""

    def __init__(
        self, message: str, *, code: str = ErrorCode.BAD_REQUEST, data: Any = None
    ) -> None:
        super().__init__(message, code=code, status_code=400, data=data)


class UnauthorizedException(BusinessException):
    """用户尚未登录，或者登录凭证已经失效。"""

    def __init__(
        self, message: str = "请先登录", *, code: str = ErrorCode.UNAUTHORIZED
    ) -> None:
        super().__init__(message, code=code, status_code=401)


class ForbiddenException(BusinessException):
    """用户已经登录，但没有执行当前操作的权限。"""

    def __init__(
        self, message: str = "没有操作权限", *, code: str = ErrorCode.FORBIDDEN
    ) -> None:
        super().__init__(message, code=code, status_code=403)


class NotFoundException(BusinessException):
    """请求的数据不存在。"""

    def __init__(
        self, message: str = "数据不存在", *, code: str = ErrorCode.NOT_FOUND
    ) -> None:
        super().__init__(message, code=code, status_code=404)


class ConflictException(BusinessException):
    """数据发生冲突，例如名称、编码或地址重复。"""

    def __init__(self, message: str, *, code: str = ErrorCode.CONFLICT) -> None:
        super().__init__(message, code=code, status_code=409)


class InternalServerException(BusinessException):
    """因为服务端配置不完整等可明确说明的原因而无法继续。"""

    def __init__(
        self, message: str, *, code: str = ErrorCode.INTERNAL_SERVER_ERROR
    ) -> None:
        super().__init__(message, code=code, status_code=500)


class ExternalServiceException(BusinessException):
    """调用 AI、订阅网站或通知服务等外部系统失败。"""

    def __init__(
        self, message: str, *, code: str = ErrorCode.EXTERNAL_SERVICE_ERROR
    ) -> None:
        super().__init__(message, code=code, status_code=502)
