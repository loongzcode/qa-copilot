import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.constants import ErrorCode
from app.exceptions.exception_base import BusinessException
from app.schemas.api_result import failure

logger = logging.getLogger(__name__)


async def business_exception_handler(
    _: Request, exc: Exception
) -> JSONResponse:
    """把 Service 抛出的业务异常转换成前端约定的统一 JSON。"""

    # Starlette 的 handler 类型要求这里接收通用 Exception。
    # 注册时已经指定只把 BusinessException 交给本函数，这里再判断一次，
    # 既帮助类型检查器识别具体类型，也避免以后被错误调用时静默出错。
    if not isinstance(exc, BusinessException):
        raise TypeError("业务异常处理器收到了错误的异常类型")

    return JSONResponse(
        status_code=exc.status_code,
        content=failure(exc.message, code=exc.code, data=exc.data).model_dump(
            mode="json", by_alias=True
        ),
        headers=exc.headers,
    )


async def http_exception_handler(
    _: Request, exc: Exception
) -> JSONResponse:
    """处理 FastAPI/Starlette 自身产生的 HTTP 错误，例如访问不存在的路由。"""

    if not isinstance(exc, StarletteHTTPException):
        raise TypeError("HTTP 异常处理器收到了错误的异常类型")

    code = ErrorCode.UNAUTHORIZED if exc.status_code == 401 else str(exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content=failure(str(exc.detail), code=code).model_dump(mode="json", by_alias=True),
        headers=exc.headers,
    )


async def validation_exception_handler(
    _: Request, exc: Exception
) -> JSONResponse:
    """处理 Pydantic 请求参数校验错误。"""

    if not isinstance(exc, RequestValidationError):
        raise TypeError("参数校验异常处理器收到了错误的异常类型")

    return JSONResponse(
        status_code=422,
        content=failure(
            "请求参数校验失败",
            code=ErrorCode.VALIDATION_ERROR,
            data=exc.errors(),
        ).model_dump(mode="json", by_alias=True),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """隐藏未知异常的内部细节，同时把完整堆栈写入服务端日志。"""

    logger.exception(
        "未处理的服务端异常 request_id=%s method=%s path=%s user_id=%s",
        getattr(request.state, "request_id", "unknown"),
        request.method,
        request.url.path,
        getattr(request.state, "user_id", None),
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content=failure("服务器内部错误", code=ErrorCode.INTERNAL_SERVER_ERROR).model_dump(
            mode="json", by_alias=True
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """集中注册异常处理器，避免 main.py 堆放具体处理逻辑。"""

    app.add_exception_handler(BusinessException, business_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
