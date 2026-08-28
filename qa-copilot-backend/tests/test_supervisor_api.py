"""Supervisor API 路由和权限码注册测试。"""

from app.core.permissions import Permission
from app.main import app


def test_supervisor_routes_are_registered() -> None:
    """创建、列表、详情、取消和启动执行接口必须注册到 FastAPI。"""
    paths = app.openapi()["paths"]

    runs_path = paths["/api/supervisor/projects/{project_id}/runs"]
    detail_path = paths["/api/supervisor/projects/{project_id}/runs/{run_id}"]
    cancel_path = paths["/api/supervisor/projects/{project_id}/runs/{run_id}/cancel"]
    execute_path = paths["/api/supervisor/projects/{project_id}/runs/{run_id}/execute"]
    approval_path = paths[
        "/api/supervisor/projects/{project_id}/runs/{run_id}/steps/{step_id}/approval"
    ]
    assert "post" in runs_path
    assert "get" in runs_path
    assert "get" in detail_path
    assert "post" in cancel_path
    assert "post" in execute_path
    assert "post" in approval_path


def test_supervisor_permissions_use_clear_codes() -> None:
    """查看和运行权限分离，避免只读角色因为能看列表就能创建计划。"""
    assert Permission.SUPERVISOR_VIEW == "supervisor:view"
    assert Permission.SUPERVISOR_RUN == "supervisor:run"
    assert Permission.SUPERVISOR_APPROVE == "supervisor:approve"
