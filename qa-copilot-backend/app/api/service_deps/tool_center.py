"""测试工具中心请求级依赖组装。"""

from typing import Annotated

from app.core.deps import DbSession
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.repositories.tool_center_repository import ToolCenterRepository
from app.services.tool_center_service import ToolCenterService
from app.services.tool_execution_service import ToolExecutionService
from app.storage.factory import get_document_storage
from fastapi import Depends


def get_tool_center_service(db: DbSession) -> ToolCenterService:
    """让工具中心与项目权限查询共享同一请求事务。"""
    return ToolCenterService(ToolCenterRepository(db), TestProjectsRepository(db))


ToolCenterServiceDep = Annotated[ToolCenterService, Depends(get_tool_center_service)]


def get_tool_execution_service(db: DbSession) -> ToolExecutionService:
    """组装受控工具执行器及统一对象存储。"""
    return ToolExecutionService(
        ToolCenterRepository(db),
        TestProjectsRepository(db),
        get_document_storage(),
        AIModelRepository(db),
    )


ToolExecutionServiceDep = Annotated[
    ToolExecutionService,
    Depends(get_tool_execution_service),
]
