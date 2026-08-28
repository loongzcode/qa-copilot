import logging
import re
import time
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)

from app.core.metrics import HTTP_REQUESTS_IN_PROGRESS, record_http_request

logger = logging.getLogger("app.http")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")

class RequestIdMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求生成并返回唯一的链路追踪编号。"""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # 网关已经生成合法链路编号时继续沿用，便于跨服务排查；非法或缺失时本服务生成。
        incoming_request_id = request.headers.get("X-Request-ID", "")
        request_id = incoming_request_id if _REQUEST_ID_PATTERN.fullmatch(incoming_request_id) else uuid4().hex
        # 2. 保存到 request.state.request_id
        request.state.request_id = request_id
        method = request.method.upper()
        started_at = time.perf_counter()
        HTTP_REQUESTS_IN_PROGRESS.labels(method).inc()
        try:
            response = await call_next(request)
        finally:
            HTTP_REQUESTS_IN_PROGRESS.labels(method).dec()
        duration_seconds = max(time.perf_counter() - started_at, 0.0)
        # 路由匹配在 call_next 返回后才完成。使用模板路径避免把每个资源 ID 变成指标标签。
        route_object = request.scope.get("route")
        route_template = getattr(route_object, "path", None) or request.url.path
        record_http_request(
            method=method,
            route=route_template,
            status_code=response.status_code,
            duration_seconds=duration_seconds,
        )
        logger.info(
            "http_request request_id=%s method=%s route=%s status=%s duration_ms=%s user_id=%s",
            request_id,
            method,
            route_template,
            response.status_code,
            round(duration_seconds * 1000),
            getattr(request.state, "user_id", None),
        )
        # 4. 将 request_id 写入响应头 X-Request-ID
        response.headers["X-Request-ID"] = request_id
        # 5. 返回响应
        return response
