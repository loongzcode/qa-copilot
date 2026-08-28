"""QA Copilot 的 Prometheus 业务指标和 Celery 任务指标。"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterable
from threading import Lock
from typing import Any

from celery import signals
from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    make_asgi_app,
    multiprocess,
    start_http_server,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# HTTP 指标使用“路由模板”作为标签，例如 /api/users/{user_id}，而不是实际 URL。
# 这样用户 ID 再多也不会生成无限数量的 Prometheus 时间序列。
HTTP_REQUESTS_TOTAL = Counter(
    "qa_copilot_http_requests_total",
    "HTTP requests grouped by method, route template and response status.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "qa_copilot_http_request_duration_seconds",
    "HTTP request duration grouped by method and route template.",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "qa_copilot_http_requests_in_progress",
    "HTTP requests currently being handled.",
    ("method",),
    multiprocess_mode="livesum",
)

# Counter（计数器）只增不减，适合计算一段时间内的调用率和失败率。
AI_MODEL_CALLS_TOTAL = Counter(
    "qa_copilot_ai_model_calls_total",
    "AI model calls grouped by task type and final status.",
    ("task_type", "status"),
)
AI_MODEL_DURATION_SECONDS = Histogram(
    "qa_copilot_ai_model_duration_seconds",
    "AI model call duration in seconds.",
    ("task_type", "status"),
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 40, 80, 160),
)
AI_MODEL_TOKENS_TOTAL = Counter(
    "qa_copilot_ai_model_tokens_total",
    "AI model tokens grouped by task type and direction.",
    ("task_type", "direction"),
)

KNOWLEDGE_INDEX_RUNS_TOTAL = Counter(
    "qa_copilot_knowledge_index_runs_total",
    "Knowledge document index runs grouped by result.",
    ("result",),
)
KNOWLEDGE_INDEX_DURATION_SECONDS = Histogram(
    "qa_copilot_knowledge_index_duration_seconds",
    "Knowledge document index duration in seconds.",
    ("result",),
    buckets=(0.5, 1, 2.5, 5, 10, 20, 40, 80, 160, 300, 600, 1200),
)

OUTBOX_PUBLISH_RESULTS_TOTAL = Counter(
    "qa_copilot_outbox_publish_results_total",
    "Transactional outbox publish results.",
    ("event_type", "result"),
)
OUTBOX_QUEUE_DEPTH = Gauge(
    "qa_copilot_outbox_queue_depth",
    "Current active transactional outbox events stored in PostgreSQL.",
    ("event_type", "status"),
    multiprocess_mode="livemostrecent",
)

CELERY_TASKS_TOTAL = Counter(
    "qa_copilot_celery_tasks_total",
    "Celery task executions grouped by task name and final state.",
    ("task_name", "state"),
)
CELERY_TASK_DURATION_SECONDS = Histogram(
    "qa_copilot_celery_task_duration_seconds",
    "Celery task execution duration in seconds.",
    ("task_name", "state"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 180, 600, 1800),
)
CELERY_TASK_RETRIES_TOTAL = Counter(
    "qa_copilot_celery_task_retries_total",
    "Celery automatic retries grouped by task and exception type.",
    ("task_name", "exception_type"),
)
CELERY_TASKS_ACTIVE = Gauge(
    "qa_copilot_celery_tasks_active",
    "Celery tasks currently running in this deployment.",
    ("task_name",),
    multiprocess_mode="livesum",
)
CELERY_BROKER_QUEUE_DEPTH = Gauge(
    "qa_copilot_celery_broker_queue_depth",
    "Current Celery tasks waiting in each Redis broker queue.",
    ("queue",),
    multiprocess_mode="livemostrecent",
)

_task_started_at: dict[str, tuple[str, float]] = {}
_task_started_at_lock = Lock()
_worker_metrics_server_started = False
_worker_metrics_server_lock = Lock()


def record_http_request(*, method: str, route: str, status_code: int, duration_seconds: float) -> None:
    """记录一次 HTTP 请求的数量和耗时，供失败率与 P95 延迟告警使用。"""

    safe_method = method.upper() or "UNKNOWN"
    safe_route = route or "unmatched"
    HTTP_REQUESTS_TOTAL.labels(safe_method, safe_route, str(status_code)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(safe_method, safe_route).observe(max(duration_seconds, 0.0))


def record_ai_model_call(
    *,
    task_type: str,
    status: str,
    latency_ms: int,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """记录一次 AI 模型调用。

    功能：累加调用结果、耗时以及输入/输出 Token。

    作用：由统一 AI 调用日志函数调用，因此文本生成、Embedding（文本向量化）和
    Rerank（检索结果重排序）不需要分别维护监控代码。

    为什么用它：集中记录能保证所有模型调用使用同一指标口径；标签只包含任务
    类型和状态，不加入用户、请求或任务 ID，避免产生海量时间序列。
    """

    safe_task_type = task_type or "unknown"
    safe_status = status or "unknown"
    AI_MODEL_CALLS_TOTAL.labels(safe_task_type, safe_status).inc()
    AI_MODEL_DURATION_SECONDS.labels(safe_task_type, safe_status).observe(
        max(latency_ms, 0) / 1000
    )
    AI_MODEL_TOKENS_TOTAL.labels(safe_task_type, "input").inc(
        max(input_tokens, 0)
    )
    AI_MODEL_TOKENS_TOTAL.labels(safe_task_type, "output").inc(
        max(output_tokens, 0)
    )


def record_knowledge_index_run(*, result: str, duration_seconds: float) -> None:
    """记录一次知识文档索引的终态和耗时。

    功能：区分成功、失败和重复任务跳过，并写入耗时直方图。

    作用：由索引 Service 在每条退出路径调用，支持计算吞吐量、失败率以及 P95
    等耗时分位数。

    为什么用它：Histogram（直方图）在服务端保存固定耗时区间，Prometheus 可
    聚合多个 Worker 并计算分位数，比只记录“最近一次耗时”更适合生产监控。
    """

    safe_result = result or "unknown"
    KNOWLEDGE_INDEX_RUNS_TOTAL.labels(safe_result).inc()
    KNOWLEDGE_INDEX_DURATION_SECONDS.labels(safe_result).observe(
        max(duration_seconds, 0.0)
    )


def record_outbox_publish_result(*, event_type: str, result: str) -> None:
    """记录一条事务性发件箱事件的发布结果。"""

    OUTBOX_PUBLISH_RESULTS_TOTAL.labels(
        event_type or "unknown",
        result or "unknown",
    ).inc()


def set_outbox_queue_depth(
    rows: Iterable[tuple[str, str, int]],
    *,
    event_types: Iterable[str],
    statuses: Iterable[str],
) -> None:
    """使用 PostgreSQL 聚合结果刷新发件箱积压量。

    功能：先把所有有限标签组合归零，再写入本轮查询到的实时数量。

    作用：由发件箱周期任务每轮发布结束后调用，让监控看到 PENDING、RETRY 和
    PROCESSING 各有多少条，而不是把进程内估算值误当成真实队列状态。

    为什么用它：发件箱状态保存在 PostgreSQL，数据库是这里的事实来源；重启
    Worker 后重新聚合即可恢复准确值。先归零可以清除已经不存在的旧状态值。
    """

    known_event_types = tuple(event_types)
    known_statuses = tuple(statuses)
    for event_type in known_event_types:
        for status in known_statuses:
            OUTBOX_QUEUE_DEPTH.labels(event_type, status).set(0)
    for event_type, status, count in rows:
        OUTBOX_QUEUE_DEPTH.labels(event_type, status).set(max(count, 0))


def set_celery_broker_queue_depth(
    rows: Iterable[tuple[str, int]],
    *,
    queue_names: Iterable[str],
) -> None:
    """使用 Redis LLEN 结果刷新真正等待消费的 Celery 任务数量。

    功能：把每个受监控 Redis List 的当前长度写入 Gauge。

    作用：由发件箱周期 Worker 刷新，和发件箱数据库积压指标配合区分“事件还没
    发布到 Redis”与“任务已经发布，但暂时没有足够 Worker 消费”两类瓶颈。

    为什么用它：项目当前没有开启 Redis 任务优先级，每个路由队列对应一个 List；
    ``LLEN`` 是 Celery 官方建议的 Redis 队列长度检查方式，读取复杂度低且不取出消息。
    """

    for queue_name in queue_names:
        CELERY_BROKER_QUEUE_DEPTH.labels(queue_name).set(0)
    for queue_name, count in rows:
        CELERY_BROKER_QUEUE_DEPTH.labels(queue_name).set(max(count, 0))


def create_metrics_asgi_app() -> Any:
    """创建 FastAPI 挂载使用的 Prometheus ASGI 指标应用。

    功能：单进程直接使用默认注册表；配置 ``PROMETHEUS_MULTIPROC_DIR`` 时改用
    多进程聚合注册表。

    作用：在主应用的 ``/metrics`` 路径输出 Prometheus 文本格式。

    为什么用它：官方 ASGI 适配器会正确处理内容类型、压缩和指标序列化；多进程
    模式则能聚合一个部署实例中的多个 Web Worker。
    """

    return make_asgi_app(registry=_create_export_registry())


def _create_export_registry() -> CollectorRegistry:
    """根据是否启用 Prometheus 多进程目录选择导出注册表。"""

    if "PROMETHEUS_MULTIPROC_DIR" not in os.environ:
        return REGISTRY
    registry = CollectorRegistry(support_collectors_without_names=True)
    multiprocess.MultiProcessCollector(registry)
    return registry


@signals.task_prerun.connect(weak=False)
def _record_celery_task_start(
    *,
    task_id: str | None = None,
    task: Any | None = None,
    **_: Any,
) -> None:
    """Celery 执行任务前保存单调时钟起点并增加正在执行数量。"""

    if not task_id:
        return
    task_name = getattr(task, "name", None) or "unknown"
    with _task_started_at_lock:
        _task_started_at[task_id] = (task_name, time.perf_counter())
    CELERY_TASKS_ACTIVE.labels(task_name).inc()


@signals.task_postrun.connect(weak=False)
def _record_celery_task_finish(
    *,
    task_id: str | None = None,
    task: Any | None = None,
    state: str | None = None,
    **_: Any,
) -> None:
    """Celery 任务结束后记录终态、耗时并减少正在执行数量。"""

    if not task_id:
        return
    fallback_task_name = getattr(task, "name", None) or "unknown"
    with _task_started_at_lock:
        started = _task_started_at.pop(task_id, None)
    task_name = started[0] if started is not None else fallback_task_name
    final_state = (state or "UNKNOWN").lower()
    CELERY_TASKS_TOTAL.labels(task_name, final_state).inc()
    if started is not None:
        CELERY_TASKS_ACTIVE.labels(task_name).dec()
        CELERY_TASK_DURATION_SECONDS.labels(task_name, final_state).observe(
            max(time.perf_counter() - started[1], 0.0)
        )


@signals.task_retry.connect(weak=False)
def _record_celery_task_retry(
    *,
    sender: Any | None = None,
    reason: BaseException | None = None,
    **_: Any,
) -> None:
    """Celery 决定重试时按任务名称和异常类型增加计数。"""

    task_name = getattr(sender, "name", None) or "unknown"
    exception_type = type(reason).__name__ if reason is not None else "unknown"
    CELERY_TASK_RETRIES_TOTAL.labels(task_name, exception_type).inc()


@signals.worker_init.connect(weak=False)
def _start_worker_metrics_server(**_: Any) -> None:
    """按配置为独立 Celery Worker 启动 Prometheus HTTP 端口。

    功能：当 ``METRICS_WORKER_PORT`` 大于 0 时启动只读指标服务。

    作用：FastAPI 和 Celery 通常部署为不同进程或容器，Worker 指标必须拥有独立
    采集端点，不能指望 FastAPI 的 ``/metrics`` 读取另一个进程的内存。

    为什么用它：Prometheus 使用拉取模式；每个 Worker 部署暴露同一个容器端口，
    由服务发现逐实例采集，比把指标同步写回业务数据库更轻量。
    """

    global _worker_metrics_server_started
    if not settings.metrics_enabled or settings.metrics_worker_port == 0:
        return
    with _worker_metrics_server_lock:
        if _worker_metrics_server_started:
            return
        start_http_server(
            port=settings.metrics_worker_port,
            addr=settings.metrics_worker_host,
            registry=_create_export_registry(),
        )
        _worker_metrics_server_started = True
        logger.info(
            "Celery Worker metrics server started on %s:%s",
            settings.metrics_worker_host,
            settings.metrics_worker_port,
        )


@signals.worker_process_shutdown.connect(weak=False)
def _mark_worker_metrics_process_dead(**_: Any) -> None:
    """多进程模式下标记当前 Worker 子进程退出，避免活动 Gauge 残留。"""

    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        multiprocess.mark_process_dead(os.getpid())
