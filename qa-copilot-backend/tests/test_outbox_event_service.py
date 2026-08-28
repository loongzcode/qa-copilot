from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.services.outbox_event_service import OutboxEventService


def _event(*, event_id: int = 7, attempts: int = 0) -> SimpleNamespace:
    """构造发布器单元测试使用的最小知识文档索引事件。"""

    return SimpleNamespace(
        id=event_id,
        event_type="KNOWLEDGE_DOCUMENT_INDEX",
        payload={"document_id": 15},
        attempt_count=attempts,
    )


def test_build_document_file_delete_message() -> None:
    """文件删除事件只能映射到固定任务，并携带受校验的对象键。"""

    event = SimpleNamespace(
        event_type="KNOWLEDGE_DOCUMENT_FILE_DELETE",
        payload={
            "document_id": 15,
            "object_key": "knowledge/3/2026/08/source.pdf",
        },
    )

    message = OutboxEventService._build_celery_message(event)

    assert message.task_name == "knowledge.delete_document_file"
    assert message.args == [15, "knowledge/3/2026/08/source.pdf"]
    assert message.kwargs == {}


def test_build_automation_execution_message() -> None:
    """自动化事件只能映射到固定执行任务，消息中只携带业务主键。"""
    event = SimpleNamespace(
        event_type="AUTOMATION_EXECUTION",
        payload={"project_id": 8, "execution_task_id": 21},
    )

    message = OutboxEventService._build_celery_message(event)

    assert message.task_name == "automation.execute"
    assert message.args == [8, 21]
    assert message.kwargs == {}


def test_build_automation_result_notification_message() -> None:
    """自动化终态通知只能进入固定通知任务，不允许事件指定任意任务名。"""
    event = SimpleNamespace(
        event_type="AUTOMATION_RESULT_NOTIFICATION",
        payload={"project_id": 8, "execution_task_id": 21},
    )

    message = OutboxEventService._build_celery_message(event)

    assert message.task_name == "notification.send_automation_result"
    assert message.args == [8, 21]
    assert message.kwargs == {}


def test_build_supervisor_execution_message() -> None:
    """Supervisor 发件箱事件只能映射到固定顺序执行任务并仅携带主键。"""
    event = SimpleNamespace(
        event_type="SUPERVISOR_EXECUTION",
        payload={"project_id": 8, "run_id": 31},
    )

    message = OutboxEventService._build_celery_message(event)

    assert message.task_name == "supervisor.execute_run"
    assert message.args == [8, 31]
    assert message.kwargs == {}


async def test_publish_batch_marks_success() -> None:
    """消息成功写入 Celery 后应记录 PUBLISHED 终态和确定性任务 ID。"""

    event = _event()
    repository = SimpleNamespace(
        claim_available_events=AsyncMock(return_value=[event]),
        mark_published=AsyncMock(return_value=True),
        mark_publish_failure=AsyncMock(),
    )
    service = OutboxEventService(repository=repository)

    with patch(
        "app.services.outbox_event_service.celery_app.send_task",
        new=Mock(return_value=SimpleNamespace(id="outbox-7")),
    ) as send_task:
        result = await service.publish_batch(publisher_id="test:1")

    assert result.claimed == 1
    assert result.published == 1
    assert result.retry_scheduled == 0
    send_task.assert_called_once_with(
        "knowledge.index_document",
        args=[15],
        kwargs={},
        task_id="outbox-7",
        retry=False,
    )
    repository.mark_published.assert_awaited_once_with(7, "outbox-7")
    repository.mark_publish_failure.assert_not_awaited()


async def test_publish_batch_schedules_retry() -> None:
    """Redis 临时异常不应丢消息，而应保存 RETRY 和下一次发送时间。"""

    event = _event(attempts=1)
    repository = SimpleNamespace(
        claim_available_events=AsyncMock(return_value=[event]),
        mark_published=AsyncMock(),
        mark_publish_failure=AsyncMock(return_value="RETRY"),
    )
    service = OutboxEventService(repository=repository)

    with patch(
        "app.services.outbox_event_service.celery_app.send_task",
        new=Mock(side_effect=ConnectionError("Redis unavailable")),
    ):
        result = await service.publish_batch(publisher_id="test:1")

    assert result.claimed == 1
    assert result.published == 0
    assert result.retry_scheduled == 1
    repository.mark_published.assert_not_awaited()
    failure_call = repository.mark_publish_failure.await_args
    assert failure_call.args == (7,)
    assert failure_call.kwargs["retry_delay_seconds"] > 0
    assert "ConnectionError" in failure_call.kwargs["error_message"]


async def test_publish_batch_rejects_unregistered_event() -> None:
    """数据库中的未知事件类型必须最终失败，不能变成任意 Celery 调用。"""

    event = _event()
    event.event_type = "RUN_ARBITRARY_TASK"
    repository = SimpleNamespace(
        claim_available_events=AsyncMock(return_value=[event]),
        mark_published=AsyncMock(),
        mark_publish_failure=AsyncMock(return_value="FAILED"),
    )
    service = OutboxEventService(repository=repository)

    with patch(
        "app.services.outbox_event_service.celery_app.send_task",
        new=Mock(),
    ) as send_task:
        result = await service.publish_batch(publisher_id="test:1")

    assert result.failed == 1
    send_task.assert_not_called()
    repository.mark_publish_failure.assert_awaited_once()
    assert repository.mark_publish_failure.await_args.kwargs["permanent"] is True
