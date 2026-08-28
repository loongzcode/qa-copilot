"""后台任务补偿扫描的 PostgreSQL 集成冒烟测试。"""

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionFactory, engine  # noqa: E402
from app.models import KnowledgeBase, KnowledgeDocument, OutboxEvent  # noqa: E402
from app.models.mixins import utc_now  # noqa: E402
from app.repositories.automation_execution_tasks_repository import (  # noqa: E402
    AutomationExecutionTasksRepository,
)
from app.repositories.knowledge_document_repository import (  # noqa: E402
    KnowledgeDocumentRepository,
)
from app.repositories.outbox_event_repository import OutboxEventRepository  # noqa: E402
from app.services.background_task_recovery_service import (  # noqa: E402
    BackgroundTaskRecoveryService,
)


async def main() -> None:
    """构造四种超时状态，执行扫描并断言恢复结果。"""

    document_ids: list[int] = []
    event_ids: list[int] = []
    old_time = utc_now() - timedelta(days=1)

    try:
        async with AsyncSessionFactory() as session:
            knowledge_base_id = await session.scalar(select(KnowledgeBase.id).limit(1))
            if knowledge_base_id is None:
                raise RuntimeError("集成测试至少需要一个知识库")

            documents = [
                # 只上传、未提交：没有 index_queued_at，扫描器必须忽略。
                KnowledgeDocument(
                    knowledge_base_id=knowledge_base_id,
                    document_type="OTHER",
                    title="outbox-smoke-upload-only",
                    source_type="MANUAL",
                    parse_status="PENDING",
                    index_recovery_count=0,
                    document_metadata={},
                    created_at=old_time,
                    updated_at=old_time,
                ),
                # 已提交但没有活动发件箱事件：应重新排队。
                KnowledgeDocument(
                    knowledge_base_id=knowledge_base_id,
                    document_type="OTHER",
                    title="outbox-smoke-pending",
                    source_type="MANUAL",
                    parse_status="PENDING",
                    index_queued_at=old_time,
                    index_recovery_count=0,
                    document_metadata={},
                    created_at=old_time,
                    updated_at=old_time,
                ),
                # 旧 Worker 心跳超时：应重新排队并清空旧任务栅栏。
                KnowledgeDocument(
                    knowledge_base_id=knowledge_base_id,
                    document_type="OTHER",
                    title="outbox-smoke-parsing",
                    source_type="MANUAL",
                    parse_status="PARSING",
                    index_task_id="old-worker-task",
                    index_queued_at=old_time,
                    index_started_at=old_time,
                    index_heartbeat_at=old_time,
                    index_recovery_count=0,
                    document_metadata={},
                    created_at=old_time,
                    updated_at=old_time,
                ),
                # 已达到恢复上限：应停止自动恢复。
                KnowledgeDocument(
                    knowledge_base_id=knowledge_base_id,
                    document_type="OTHER",
                    title="outbox-smoke-exhausted",
                    source_type="MANUAL",
                    parse_status="INDEXING",
                    index_task_id="exhausted-worker-task",
                    index_queued_at=old_time,
                    index_started_at=old_time,
                    index_heartbeat_at=old_time,
                    index_recovery_count=settings.knowledge_document_max_recoveries,
                    document_metadata={},
                    created_at=old_time,
                    updated_at=old_time,
                ),
            ]
            session.add_all(documents)
            await session.flush()
            document_ids = [document.id for document in documents]

            stale_outbox = OutboxEvent(
                event_type="KNOWLEDGE_DOCUMENT_INDEX",
                aggregate_type="KNOWLEDGE_DOCUMENT",
                aggregate_id=1_999_999_999,
                payload={"document_id": 1_999_999_999},
                status="PROCESSING",
                attempt_count=0,
                max_attempts=2,
                locked_at=old_time,
                locked_by="dead-publisher",
            )
            session.add(stale_outbox)
            await session.commit()
            event_ids.append(stale_outbox.id)

        async with AsyncSessionFactory() as session:
            service = BackgroundTaskRecoveryService(
                knowledge_document_repository=KnowledgeDocumentRepository(session),
                outbox_event_repository=OutboxEventRepository(session),
                automation_execution_repository=AutomationExecutionTasksRepository(session),
            )
            result = await service.recover()

        async with AsyncSessionFactory() as session:
            recovered_documents = list(
                (
                    await session.scalars(
                        select(KnowledgeDocument)
                        .where(KnowledgeDocument.id.in_(document_ids))
                        .order_by(KnowledgeDocument.id)
                    )
                ).all()
            )
            active_events = list(
                (
                    await session.scalars(
                        select(OutboxEvent).where(
                            OutboxEvent.aggregate_id.in_(document_ids)
                        )
                    )
                ).all()
            )
            event_ids.extend(event.id for event in active_events)
            stale_event = await session.get(OutboxEvent, event_ids[0])

        upload_only, pending, parsing, exhausted = recovered_documents
        assert upload_only.index_queued_at is None
        assert upload_only.index_recovery_count == 0
        assert pending.parse_status == "PENDING"
        assert pending.index_recovery_count == 1
        assert parsing.parse_status == "PENDING"
        assert parsing.index_task_id is None
        assert exhausted.parse_status == "FAILED"
        assert len(active_events) == 2
        assert stale_event is not None and stale_event.status == "RETRY"
        assert result.documents_requeued == 2
        assert result.documents_failed == 1
        assert result.documents_rebuild_queued == 0
        assert result.outbox_retried == 1

        # 旧任务编号已被清空，因此旧 Worker 不能再把文档推进到 READY。
        async with AsyncSessionFactory() as session:
            old_worker_updated = await KnowledgeDocumentRepository(
                session
            ).mark_parse_status(
                parsing.id,
                "old-worker-task",
                "READY",
            )
        assert old_worker_updated is False
        print("Background recovery smoke passed:", result)
    finally:
        async with AsyncSessionFactory() as session:
            if event_ids:
                await session.execute(
                    delete(OutboxEvent).where(OutboxEvent.id.in_(event_ids))
                )
            if document_ids:
                await session.execute(
                    delete(KnowledgeDocument).where(
                        KnowledgeDocument.id.in_(document_ids)
                    )
                )
            await session.commit()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
