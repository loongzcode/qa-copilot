"""Pytest 固定入口；该文件不接受和执行任何动态 Python 源码。"""

import json
from pathlib import Path
from typing import Any

from app.automation.controlled_http_runner import execute_controlled_http_test


def test_controlled_automation_definition(
    automation_runtime: dict[str, Any],
    automation_output_path: Path,
) -> None:
    """运行一次受控定义、写出最小结论，并由 Pytest 判定整体是否通过。"""
    result = execute_controlled_http_test(automation_runtime)
    automation_output_path.write_text(
        json.dumps(result, ensure_ascii=False),
        encoding="utf-8",
    )
    assert result["success"], result["message"]
