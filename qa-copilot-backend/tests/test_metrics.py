"""Prometheus 指标埋点与导出端点测试。"""

from types import SimpleNamespace

from app.core.metrics import (
    AI_MODEL_CALLS_TOTAL,
    CELERY_BROKER_QUEUE_DEPTH,
    CELERY_TASK_RETRIES_TOTAL,
    HTTP_REQUESTS_TOTAL,
    KNOWLEDGE_INDEX_RUNS_TOTAL,
    OUTBOX_QUEUE_DEPTH,
    _record_celery_task_retry,
    record_ai_model_call,
    record_knowledge_index_run,
    set_celery_broker_queue_depth,
    set_outbox_queue_depth,
)
from app.main import app
from fastapi.testclient import TestClient


def test_business_metrics_are_recorded_and_exported() -> None:
    """业务埋点增加后，Prometheus 端点必须输出对应时间序列。"""

    ai_counter = AI_MODEL_CALLS_TOTAL.labels("metrics_test", "success")
    index_counter = KNOWLEDGE_INDEX_RUNS_TOTAL.labels("metrics_test")
    retry_counter = CELERY_TASK_RETRIES_TOTAL.labels(
        "metrics.test_task",
        "TimeoutError",
    )
    ai_before = ai_counter._value.get()
    index_before = index_counter._value.get()
    retry_before = retry_counter._value.get()

    record_ai_model_call(
        task_type="metrics_test",
        status="success",
        latency_ms=250,
        input_tokens=12,
        output_tokens=4,
    )
    record_knowledge_index_run(
        result="metrics_test",
        duration_seconds=1.5,
    )
    _record_celery_task_retry(
        sender=SimpleNamespace(name="metrics.test_task"),
        reason=TimeoutError("test timeout"),
    )
    set_outbox_queue_depth(
        [("KNOWLEDGE_DOCUMENT_INDEX", "PENDING", 3)],
        event_types=("KNOWLEDGE_DOCUMENT_INDEX",),
        statuses=("PENDING", "PROCESSING", "RETRY"),
    )
    set_celery_broker_queue_depth(
        [("knowledge-index", 2)],
        queue_names=("knowledge-index", "knowledge-memory"),
    )

    assert ai_counter._value.get() == ai_before + 1
    assert index_counter._value.get() == index_before + 1
    assert retry_counter._value.get() == retry_before + 1
    assert (
        OUTBOX_QUEUE_DEPTH.labels(
            "KNOWLEDGE_DOCUMENT_INDEX",
            "PENDING",
        )._value.get()
        == 3
    )
    assert CELERY_BROKER_QUEUE_DEPTH.labels("knowledge-index")._value.get() == 2
    assert CELERY_BROKER_QUEUE_DEPTH.labels("knowledge-memory")._value.get() == 0

    response = TestClient(app).get("/metrics/", follow_redirects=True)
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "qa_copilot_ai_model_calls_total" in response.text
    assert "qa_copilot_knowledge_index_duration_seconds" in response.text
    assert "qa_copilot_celery_task_retries_total" in response.text
    assert "qa_copilot_outbox_queue_depth" in response.text
    assert "qa_copilot_celery_broker_queue_depth" in response.text


def test_http_request_uses_safe_route_template_and_request_id() -> None:
    """HTTP 中间件必须返回链路编号，并按有限路由模板记录请求指标。"""

    counter = HTTP_REQUESTS_TOTAL.labels("GET", "/health", "200")
    before = counter._value.get()
    response = TestClient(app).get("/health", headers={"X-Request-ID": "gateway-trace-123456"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "gateway-trace-123456"
    assert counter._value.get() == before + 1
