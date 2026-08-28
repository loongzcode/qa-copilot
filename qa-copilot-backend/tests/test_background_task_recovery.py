from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.core.config import settings
from app.services.background_task_recovery_service import (
    BackgroundTaskRecoveryService,
)


def _automation_repository() -> SimpleNamespace:
    """为知识文档补偿测试提供没有超时自动化任务的依赖。"""
    return SimpleNamespace(finish_stale_tasks=AsyncMock(return_value=(0, 0)))


async def test_recovery_requeues_and_stops_exhausted_documents() -> None:
    """可恢复文档应重新排队，达到上限的文档应进入 FAILED。"""

    pending_document = SimpleNamespace(
        id=11,
        parse_status="PENDING",
        error_message=None,
        index_task_id=None,
        index_queued_at=None,
        index_started_at=None,
        index_heartbeat_at=None,
        index_completed_at=None,
        index_recovery_count=0,
    )
    stuck_document = SimpleNamespace(
        id=12,
        parse_status="INDEXING",
        error_message=None,
        index_task_id="old-task",
        index_queued_at=None,
        index_started_at=None,
        index_heartbeat_at=None,
        index_completed_at=None,
        index_recovery_count=settings.knowledge_document_max_recoveries,
    )
    knowledge_repository = SimpleNamespace(
        lock_stale_index_documents=AsyncMock(
            return_value=[pending_document, stuck_document]
        ),
        lock_documents_requiring_reindex=AsyncMock(return_value=[]),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    outbox_repository = SimpleNamespace(
        recover_stale_processing_events=AsyncMock(return_value=(1, 0)),
        add_pending_event=Mock(),
    )
    service = BackgroundTaskRecoveryService(
        knowledge_document_repository=knowledge_repository,
        outbox_event_repository=outbox_repository,
        automation_execution_repository=_automation_repository(),
    )

    result = await service.recover()

    assert result.outbox_retried == 1
    assert result.documents_requeued == 1
    assert result.documents_failed == 1
    assert result.documents_rebuild_queued == 0
    assert pending_document.parse_status == "PENDING"
    assert pending_document.index_recovery_count == 1
    assert pending_document.index_task_id is None
    assert stuck_document.parse_status == "FAILED"
    assert "停止自动恢复" in stuck_document.error_message
    outbox_repository.add_pending_event.assert_called_once_with(
        event_type="KNOWLEDGE_DOCUMENT_INDEX",
        aggregate_type="KNOWLEDGE_DOCUMENT",
        aggregate_id=11,
        payload={"document_id": 11},
    )
    knowledge_repository.commit.assert_awaited_once()


async def test_recovery_rolls_back_empty_document_scan() -> None:
    """没有超时文档时应结束查询事务且不创建发件箱事件。"""

    knowledge_repository = SimpleNamespace(
        lock_stale_index_documents=AsyncMock(return_value=[]),
        lock_documents_requiring_reindex=AsyncMock(return_value=[]),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    outbox_repository = SimpleNamespace(
        recover_stale_processing_events=AsyncMock(return_value=(0, 0)),
        add_pending_event=Mock(),
    )
    service = BackgroundTaskRecoveryService(
        knowledge_document_repository=knowledge_repository,
        outbox_event_repository=outbox_repository,
        automation_execution_repository=_automation_repository(),
    )

    result = await service.recover()

    assert result.documents_requeued == 0
    assert knowledge_repository.rollback.await_count == 2
    knowledge_repository.commit.assert_not_awaited()
    outbox_repository.add_pending_event.assert_not_called()


async def test_recovery_queues_documents_with_incompatible_index() -> None:
    """模型或版本变化属于正常重建，不应增加故障恢复次数。"""

    rebuild_document = SimpleNamespace(
        id=21,
        parse_status="READY",
        error_message=None,
        index_task_id="old-finished-task",
        index_queued_at=None,
        index_started_at=None,
        index_heartbeat_at=None,
        index_completed_at=None,
        index_recovery_count=2,
    )
    knowledge_repository = SimpleNamespace(
        lock_stale_index_documents=AsyncMock(return_value=[]),
        lock_documents_requiring_reindex=AsyncMock(
            return_value=[rebuild_document]
        ),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    outbox_repository = SimpleNamespace(
        recover_stale_processing_events=AsyncMock(return_value=(0, 0)),
        add_pending_event=Mock(),
    )
    service = BackgroundTaskRecoveryService(
        knowledge_document_repository=knowledge_repository,
        outbox_event_repository=outbox_repository,
        automation_execution_repository=_automation_repository(),
    )

    result = await service.recover()

    assert result.documents_rebuild_queued == 1
    assert rebuild_document.parse_status == "PENDING"
    assert rebuild_document.index_recovery_count == 0
    assert rebuild_document.index_task_id is None
    assert "完整重建" in rebuild_document.error_message
    outbox_repository.add_pending_event.assert_called_once_with(
        event_type="KNOWLEDGE_DOCUMENT_INDEX",
        aggregate_type="KNOWLEDGE_DOCUMENT",
        aggregate_id=21,
        payload={"document_id": 21},
    )


async def test_recovery_requeues_stale_supervisor_run_with_limited_counter() -> None:
    """失联 Supervisor 运行应重新写发件箱，并增加有限恢复计数。"""
    knowledge_repository = SimpleNamespace(
        lock_stale_index_documents=AsyncMock(return_value=[]),
        lock_documents_requiring_reindex=AsyncMock(return_value=[]),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    outbox_repository = SimpleNamespace(
        recover_stale_processing_events=AsyncMock(return_value=(0, 0)),
        has_active_event=AsyncMock(return_value=False),
        add_pending_event=Mock(),
    )
    stale_run = SimpleNamespace(
        id=31,
        project_id=8,
        execution_recovery_count=0,
        steps=[],
    )
    supervisor_repository = SimpleNamespace(
        lock_stale_running_runs=AsyncMock(return_value=[stale_run]),
        mark_running_requeued=AsyncMock(return_value=True),
        transition_step=AsyncMock(return_value=True),
        transition_run=AsyncMock(return_value=True),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    service = BackgroundTaskRecoveryService(
        knowledge_document_repository=knowledge_repository,
        outbox_event_repository=outbox_repository,
        automation_execution_repository=_automation_repository(),
        supervisor_repository=supervisor_repository,
    )

    result = await service.recover()

    assert result.supervisor_runs_requeued == 1
    assert result.supervisor_runs_failed == 0
    outbox_repository.add_pending_event.assert_called_once_with(
        event_type="SUPERVISOR_EXECUTION",
        aggregate_type="SUPERVISOR_RUN",
        aggregate_id=31,
        payload={"project_id": 8, "run_id": 31},
    )
    supervisor_repository.mark_running_requeued.assert_awaited_once_with(8, 31)
    supervisor_repository.commit.assert_awaited_once()
