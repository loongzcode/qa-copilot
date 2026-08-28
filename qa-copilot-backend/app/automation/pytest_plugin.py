"""向固定 Pytest 入口注入一次受控运行输入和输出路径。"""

import json
from pathlib import Path
from typing import Any

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """注册仅由 Worker 子进程传入的输入和输出文件参数。"""
    group = parser.getgroup("qa-copilot-automation")
    group.addoption("--automation-input", required=True)
    group.addoption("--automation-output", required=True)


@pytest.fixture
def automation_runtime(request: pytest.FixtureRequest) -> dict[str, Any]:
    """从 Worker 创建的临时文件读取运行输入；测试结束后由父进程删除目录。"""
    path = Path(str(request.config.getoption("--automation-input")))
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def automation_output_path(request: pytest.FixtureRequest) -> Path:
    """返回固定测试入口写入机器可读结论的位置。"""
    return Path(str(request.config.getoption("--automation-output")))
