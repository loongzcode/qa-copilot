"""Celery Worker 共享事件循环的回归测试。"""

from __future__ import annotations

import asyncio

from app.workers import async_runtime


async def _current_loop_identity() -> int:
    """返回当前协程所属循环的对象编号，供测试比较。"""

    return id(asyncio.get_running_loop())


def test_worker_coroutines_share_one_event_loop() -> None:
    """不同后台任务依次执行时必须复用同一循环，避免数据库连接跨循环。"""

    try:
        first_loop = async_runtime.run_worker_coroutine(
            _current_loop_identity()
        )
        second_loop = async_runtime.run_worker_coroutine(
            _current_loop_identity()
        )

        assert first_loop == second_loop
        assert first_loop == id(async_runtime.get_worker_event_loop())
    finally:
        async_runtime.shutdown_worker_async_runtime()
