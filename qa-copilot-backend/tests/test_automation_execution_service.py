"""FR-AUTO-002 总超时、取消和提交边界测试。"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from app.core.constants import AutomationExecutionStatus
from app.exceptions import BadRequestException, ForbiddenException
from app.schemas.dto.automation_execution_tasks import AutomationExecutionCreateDTO
from app.services.automation_execution_service import AutomationExecutionService


class _SlowHandler(BaseHTTPRequestHandler):
    """提供一个不会立即响应的端点，用于验证父进程能强制终止执行。"""

    def log_message(self, *_: object) -> None:
        """关闭测试访问日志。"""

    def do_GET(self) -> None:  # noqa: N802
        # 比测试任务总超时更长，确保终态来自父进程，而不是 HTTPX 自身。
        threading.Event().wait(3)
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _RuntimeRepository:
    """只实现子进程轮询需要的取消状态查询。"""

    def __init__(self, cancel_requested: bool = False) -> None:
        self.cancel_requested = cancel_requested

    async def is_cancel_requested(self, _task_id: int) -> bool:
        return self.cancel_requested


def _runtime(base_url: str) -> dict:
    return {
        "baseUrl": base_url,
        "headers": {},
        "variables": {},
        "maxResponseBytes": 100_000,
        "definition": {
            "schemaVersion": "1.0",
            "steps": [
                {
                    "name": "慢请求",
                    "request": {"method": "GET", "path": "/slow", "timeoutSeconds": 10},
                    "assertions": [{"type": "STATUS_CODE", "expected": 200}],
                    "extractors": [],
                }
            ],
        },
    }


def _run_with_server(cancel_requested: bool, timeout_seconds: int) -> AutomationExecutionStatus:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    repository = _RuntimeRepository(cancel_requested)
    service = AutomationExecutionService(repository, None, None, None)  # type: ignore[arg-type]
    task = SimpleNamespace(id=99, timeout_seconds=timeout_seconds)
    try:
        status, _, _ = asyncio.run(
            service._run_pytest_subprocess(  # noqa: SLF001
                task,  # type: ignore[arg-type]
                _runtime(f"http://127.0.0.1:{server.server_port}"),
            )
        )
        return status
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=4)


def test_parent_process_enforces_total_timeout() -> None:
    """整次任务到达总超时后必须杀死 Pytest，而不是继续占用 Worker。"""
    assert _run_with_server(cancel_requested=False, timeout_seconds=1) == AutomationExecutionStatus.TIMED_OUT


def test_cancel_request_terminates_pytest_subprocess() -> None:
    """数据库出现取消请求后必须终止 Pytest 并写入 CANCELLED。"""
    assert _run_with_server(cancel_requested=True, timeout_seconds=10) == AutomationExecutionStatus.CANCELLED


class _SubmissionRepository:
    def __init__(self, definition: object, environment: object) -> None:
        self.definition = definition
        self.environment = environment

    async def get_submission_assets(self, *_: object) -> tuple[object, object]:
        return self.definition, self.environment


class _ProjectRepository:
    async def get_accessible_project(self, *_: object) -> object:
        return object()


def _submit_with_assets(definition_status: str, *, enabled: bool, environment_type: str) -> None:
    definition = SimpleNamespace(status=definition_status)
    environment = SimpleNamespace(enabled=enabled, environment_type=environment_type)
    service = AutomationExecutionService(
        _SubmissionRepository(definition, environment),  # type: ignore[arg-type]
        _ProjectRepository(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
    )
    asyncio.run(
        service.submit_task(
            1,
            AutomationExecutionCreateDTO(definition_id=1, environment_id=1, timeout_seconds=10),
            SimpleNamespace(id=1),  # type: ignore[arg-type]
        )
    )


def test_rejects_unapproved_definition() -> None:
    with pytest.raises(BadRequestException, match="只有已审批"):
        _submit_with_assets("DRAFT", enabled=True, environment_type="TEST")


def test_rejects_disabled_environment() -> None:
    with pytest.raises(BadRequestException, match="已停用"):
        _submit_with_assets("APPROVED", enabled=False, environment_type="TEST")


def test_rejects_production_environment() -> None:
    with pytest.raises(ForbiddenException, match="禁止连接生产环境"):
        _submit_with_assets("APPROVED", enabled=True, environment_type="PRODUCTION")
