"""MCP 管理服务依赖组装。"""

from typing import Annotated

from app.api.service_deps.quality_delivery import get_quality_delivery_service
from app.api.service_deps.requirements import get_requirements_service
from app.api.service_deps.test_cases import get_test_cases_service
from app.api.service_deps.test_projects import get_test_projects_service
from app.core.deps import DbSession
from app.services.mcp_management_service import McpManagementService
from fastapi import Depends


def get_mcp_management_service(db: DbSession) -> McpManagementService:
    """让四个既有业务 Service 共用当前请求或 MCP 调用的数据库 Session。"""

    return McpManagementService(
        get_test_projects_service(db),
        get_requirements_service(db),
        get_test_cases_service(db),
        get_quality_delivery_service(db),
    )


McpManagementServiceDep = Annotated[
    McpManagementService,
    Depends(get_mcp_management_service),
]
