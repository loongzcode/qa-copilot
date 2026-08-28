"""自动化终态与通知发件箱的事务边界测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.core.constants import AutomationExecutionStatus
from app.services.automation_execution_service import AutomationExecutionService


async def test_finish_task_and_notification_event_share_one_commit() -> None:
    """任务终态先 flush，通知事件加入同一 Session 后才允许统一 commit。"""
    repository = SimpleNamespace(
        finish_task=AsyncMock(return_value=True),
        commit=AsyncMock(),
    )
    outbox_repository = SimpleNamespace(add_pending_event=Mock())
    service = AutomationExecutionService(
        repository,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        outbox_repository,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
    )

    saved = await service._finish_task_with_notification(  # noqa: SLF001
        8,
        21,
        AutomationExecutionStatus.FAILED,
        error_message="断言失败",
    )

    assert saved is True
    assert repository.finish_task.await_args.kwargs["commit"] is False
    outbox_repository.add_pending_event.assert_called_once()
    assert outbox_repository.add_pending_event.call_args.kwargs["payload"] == {
        "project_id": 8,
        "execution_task_id": 21,
    }
    repository.commit.assert_awaited_once()
