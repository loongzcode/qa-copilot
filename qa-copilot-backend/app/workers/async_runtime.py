"""Celery 同步任务共用的异步运行环境。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from celery import signals

from app.core.database import engine

logger = logging.getLogger(__name__)

AsyncCleanup = Callable[[], Awaitable[None]]

_worker_event_loop: asyncio.AbstractEventLoop | None = None
_cleanup_callbacks: list[AsyncCleanup] = []


def get_worker_event_loop() -> asyncio.AbstractEventLoop:
    """取得当前 Celery Worker 进程唯一的 asyncio 事件循环。

    功能：第一次执行异步任务时创建事件循环，后续所有任务类型复用同一个循环。
    作用：把 Celery 的同步任务入口连接到异步 SQLAlchemy、asyncpg 和模型调用。
    为什么用它：SQLAlchemy 的异步连接池会保存绑定到事件循环的 asyncpg 连接；
    如果需求拆解、用例生成等模块各建一个循环却共用连接池，就会出现
    ``Future attached to a different loop``。统一循环可从根源消除跨循环复用。
    """

    global _worker_event_loop
    if _worker_event_loop is None or _worker_event_loop.is_closed():
        _worker_event_loop = asyncio.new_event_loop()
        # 同步库在协程外调用 get_event_loop() 时也应取得同一个 Worker 循环。
        asyncio.set_event_loop(_worker_event_loop)
    return _worker_event_loop


def run_worker_coroutine[ResultT](coroutine: Awaitable[ResultT]) -> ResultT:
    """在 Worker 共享事件循环中执行一个协程并返回结果。

    功能：运行异步 Service，直到它成功返回或抛出原异常。
    作用：所有 Celery Task 都通过这一入口桥接异步业务，避免自行管理循环。
    为什么用它：集中管理可保证数据库连接池与事件循环生命周期一致，也让退出
    清理只有一个实现；替代方案是每个任务使用 NullPool 新建连接，但连接成本更高。
    """

    return get_worker_event_loop().run_until_complete(coroutine)


def register_worker_cleanup(callback: AsyncCleanup) -> None:
    """注册需要在 Worker 退出前执行的异步资源清理方法。

    功能：收集 Redis 客户端等除数据库连接池之外的异步清理回调。
    作用：共享运行环境关闭事件循环前，按注册顺序的反序执行这些回调。
    为什么用它：异步资源必须在原事件循环仍存活时关闭；分散的 Celery 退出信号
    无法保证先后顺序，可能先关闭循环再清理资源。
    """

    if callback not in _cleanup_callbacks:
        _cleanup_callbacks.append(callback)


@signals.worker_process_shutdown.connect
def shutdown_worker_async_runtime(**_: object) -> None:
    """Worker 进程退出时统一关闭异步资源、数据库连接池和事件循环。

    功能：执行已注册清理回调、释放 SQLAlchemy Engine，最后关闭共享循环。
    作用：这是共享运行环境的生命周期终点，由 Celery 退出信号自动调用。
    为什么用它：必须先在原循环中关闭异步资源，再关闭循环；否则会留下连接或
    出现 ``Event loop is closed``。单一处理器还能避免多个模块重复 dispose。
    """

    global _worker_event_loop
    if _worker_event_loop is None or _worker_event_loop.is_closed():
        return

    for callback in reversed(_cleanup_callbacks):
        try:
            _worker_event_loop.run_until_complete(callback())
        except Exception:
            # 退出清理失败不能阻止后面的数据库连接和事件循环继续释放。
            logger.exception("Celery Worker 异步资源清理失败")
    _worker_event_loop.run_until_complete(engine.dispose())
    _worker_event_loop.close()
    _worker_event_loop = None
    asyncio.set_event_loop(None)
