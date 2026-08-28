"""固定 HTTPX 解释器的真实本地 HTTP 回归测试。"""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from app.automation.controlled_http_runner import execute_controlled_http_test


class _Handler(BaseHTTPRequestHandler):
    """提供登录取 Token 和鉴权查询两个受控测试端点。"""

    def log_message(self, *_: object) -> None:
        """测试期间关闭标准库访问日志，避免污染测试输出。"""

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/login":
            self._write_json(200, {"data": {"token": "runtime-token"}})
        else:
            self._write_json(404, {"message": "not found"})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/articles" and self.headers.get("Authorization") == "Bearer runtime-token":
            self._write_json(200, {"data": {"records": [1]}})
        else:
            self._write_json(401, {"message": "unauthorized"})


def _runtime(base_url: str) -> dict:
    """构造两步登录流程，验证提取变量会传递给后续请求。"""
    return {
        "baseUrl": base_url,
        "headers": {},
        "variables": {"username": "tester", "password": "secret"},
        "maxResponseBytes": 100_000,
        "definition": {
            "schemaVersion": "1.0",
            "steps": [
                {
                    "name": "登录",
                    "request": {
                        "method": "POST",
                        "path": "/login",
                        "jsonBody": {"username": "{{username}}", "password": "{{password}}"},
                    },
                    "assertions": [{"type": "STATUS_CODE", "expected": 200}],
                    "extractors": [
                        {"name": "access_token", "source": "JSON_BODY", "expression": "$.data.token"}
                    ],
                },
                {
                    "name": "查询文章",
                    "request": {
                        "method": "GET",
                        "path": "/articles",
                        "headers": {"Authorization": "Bearer {{access_token}}"},
                    },
                    "assertions": [
                        {"type": "STATUS_CODE", "expected": 200},
                        {"type": "JSON_PATH_EXISTS", "expression": "$.data.records"},
                    ],
                },
            ],
        },
    }


def test_executes_multi_step_http_definition() -> None:
    """固定解释器应顺序完成登录、变量提取和后续鉴权请求。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = execute_controlled_http_test(_runtime(f"http://127.0.0.1:{server.server_port}"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result["success"] is True
    assert result["passedSteps"] == 2
    assert result["failedSteps"] == 0
    assert result["skippedSteps"] == 0
    assert [step["status"] for step in result["steps"]] == ["PASSED", "PASSED"]
    assert result["steps"][0]["requestSummary"]["bodyFieldNames"] == ["password", "username"]
    assert "body" not in result["steps"][0]["responseSummary"]


def test_returns_safe_assertion_failure() -> None:
    """断言失败只返回步骤和断言类型，不回显请求密钥或响应正文。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    runtime = _runtime(f"http://127.0.0.1:{server.server_port}")
    runtime["definition"]["steps"][0]["assertions"][0]["expected"] = 201
    try:
        result = execute_controlled_http_test(runtime)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result["success"] is False
    assert result["failedStep"] == 1
    assert result["failedSteps"] == 1
    assert result["skippedSteps"] == 1
    assert [step["status"] for step in result["steps"]] == ["FAILED", "SKIPPED"]
    assert result["steps"][0]["assertions"][0]["actual"] == 200
    assert "secret" not in json.dumps(result)
    assert "runtime-token" not in json.dumps(result)


def test_fixed_pytest_entry_runs_in_isolated_subprocess() -> None:
    """真实启动 Worker 使用的固定 Pytest 命令，防止项目级插件参数污染运行时。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    test_temp_root = Path(__file__).resolve().parents[1] / "data" / "automation-executions"
    test_temp_root.mkdir(parents=True, exist_ok=True)
    try:
        with TemporaryDirectory(prefix="qa-auto-test-", dir=test_temp_root) as temp_dir:
            input_path = Path(temp_dir) / "input.json"
            output_path = Path(temp_dir) / "output.json"
            input_path.write_text(
                json.dumps(_runtime(f"http://127.0.0.1:{server.server_port}")),
                encoding="utf-8",
            )
            environment = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-o",
                    "addopts=",
                    "-p",
                    "app.automation.pytest_plugin",
                    "app/automation/controlled_pytest_case.py",
                    "--automation-input",
                    os.fspath(input_path),
                    "--automation-output",
                    os.fspath(output_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            assert completed.returncode == 0, completed.stdout + completed.stderr
            result = json.loads(output_path.read_text(encoding="utf-8"))
            assert result["success"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
