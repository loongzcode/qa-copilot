from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ai_model_api import router as ai_model_router
from app.api.ai_provider_api import router as ai_provider_router
from app.api.ai_usage_logs_api import router as ai_usage_logs_router
from app.api.auth_api import router as auth_router
from app.api.automation_definitions_api import router as automation_definitions_router
from app.api.automation_execution_tasks_api import router as automation_execution_tasks_router
from app.api.automation_schedules_api import router as automation_schedules_router
from app.api.knowledge_base_api import router as knowledge_base_router
from app.api.knowledge_chat_api import router as knowledge_chat_router
from app.api.knowledge_document_api import router as knowledge_document_router
from app.api.mcp_management_api import router as mcp_management_router
from app.api.menu_api import router as menu_router
from app.api.notification_channels_api import router as notification_channels_router
from app.api.prompt_template_api import router as prompt_templates_router
from app.api.quality_delivery_api import router as quality_delivery_router
from app.api.requirement_extraction_api import router as requirement_extraction_router
from app.api.requirement_items_api import router as requirement_items_router
from app.api.requirements_api import router as requirements_router
from app.api.role_api import router as role_router
from app.api.route_api import router as route_router
from app.api.supervisor_api import router as supervisor_router
from app.api.test_cases_api import (
    requirement_case_router,
)
from app.api.test_cases_api import (
    router as test_cases_router,
)
from app.api.test_environments_api import router as test_environments_router
from app.api.test_modules_api import router as test_modules_router
from app.api.test_project_members_api import router as test_project_members_router
from app.api.test_projects_api import router as test_projects_router
from app.api.tool_center_api import router as tool_center_router
from app.api.user_api import router as user_router
from app.core.config import settings
from app.core.metrics import create_metrics_asgi_app
from app.core.request_id import RequestIdMiddleware
from app.exceptions.exception_handlers import register_exception_handlers
from app.mcp_server import MCP_HTTP_APP, MCP_SERVER
from app.schemas.api_result import success


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """启动 MCP 会话管理器，并在 FastAPI 停止时一并释放其后台资源。"""

    if not settings.mcp_enabled:
        yield
        return
    async with MCP_SERVER.session_manager.run():
        yield

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
)


# 添加跨域中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Mcp-Session-Id"],
)
app.add_middleware(RequestIdMiddleware)

# Prometheus 使用拉取模式访问该端点。指标接口不包装 ApiResult，否则监控服务
# 无法识别 Prometheus 文本协议。
if settings.metrics_enabled:
    app.mount("/metrics", create_metrics_asgi_app())


# 健康检查接口
@app.get("/health")
async def health() -> dict:
    return success({"status": "ok"}).model_dump(mode="json", by_alias=True)


# 注册异常处理器
register_exception_handlers(app)

# 注册路由
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(route_router, prefix=settings.api_prefix)
app.include_router(user_router, prefix=settings.api_prefix)
app.include_router(role_router, prefix=settings.api_prefix)
app.include_router(menu_router, prefix=settings.api_prefix)
app.include_router(ai_provider_router, prefix=settings.api_prefix)
app.include_router(ai_model_router, prefix=settings.api_prefix)
app.include_router(notification_channels_router, prefix=settings.api_prefix)
app.include_router(test_projects_router, prefix=settings.api_prefix)
app.include_router(test_project_members_router, prefix=settings.api_prefix)
app.include_router(test_modules_router, prefix=settings.api_prefix)
app.include_router(test_environments_router, prefix=settings.api_prefix)

app.include_router(knowledge_base_router, prefix=settings.api_prefix)
app.include_router(knowledge_document_router, prefix=settings.api_prefix)

app.include_router(prompt_templates_router, prefix=settings.api_prefix)
app.include_router(knowledge_chat_router, prefix=settings.api_prefix)
app.include_router(ai_usage_logs_router, prefix=settings.api_prefix)
app.include_router(
    requirements_router,
    prefix=settings.api_prefix,
)
app.include_router(
    requirement_items_router,
    prefix=settings.api_prefix,
)
app.include_router(
    requirement_extraction_router,
    prefix=settings.api_prefix,
)
app.include_router(test_cases_router, prefix=settings.api_prefix)
app.include_router(requirement_case_router, prefix=settings.api_prefix)
app.include_router(automation_definitions_router, prefix=settings.api_prefix)
app.include_router(automation_execution_tasks_router, prefix=settings.api_prefix)
app.include_router(automation_schedules_router, prefix=settings.api_prefix)
app.include_router(tool_center_router, prefix=settings.api_prefix)
app.include_router(quality_delivery_router, prefix=settings.api_prefix)
app.include_router(supervisor_router, prefix=settings.api_prefix)
app.include_router(mcp_management_router, prefix=settings.api_prefix)

# Streamable HTTP 是当前 MCP 的标准远程传输方式；结尾斜杠属于挂载后的真实端点。
if settings.mcp_enabled:
    app.mount(f"{settings.api_prefix}/mcp", MCP_HTTP_APP)
