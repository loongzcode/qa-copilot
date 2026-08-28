from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.core.config import settings
from app.core.constants import (
    KNOWLEDGE_DOCUMENT_INDEX_VERSION,
    KNOWLEDGE_EMBEDDING_DIMENSIONS,
    KnowledgeDocumentParseStatus,
    OutboxAggregateType,
    OutboxEventType,
    SupervisorExecutionStepStatus,
    SupervisorRunStatus,
)
from app.models.mixins import utc_now
from app.repositories.automation_execution_tasks_repository import AutomationExecutionTasksRepository
from app.repositories.background_recovery_repository import BackgroundRecoveryRepository
from app.repositories.knowledge_document_repository import KnowledgeDocumentRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.supervisor_repository import SupervisorRepository


@dataclass(frozen=True, slots=True)
class BackgroundRecoveryResult:
    """一轮后台任务补偿扫描的统计结果。"""

    outbox_retried: int
    outbox_failed: int
    documents_requeued: int
    documents_failed: int
    documents_rebuild_queued: int
    automation_tasks_timed_out: int
    automation_tasks_cancelled: int
    requirement_tasks_failed: int
    case_generation_tasks_failed: int
    memory_summaries_failed: int
    tool_tasks_failed: int
    supervisor_runs_requeued: int
    supervisor_runs_failed: int


class BackgroundTaskRecoveryService:
    """恢复事务性发件箱和知识文档索引中的超时任务。"""

    def __init__(
        self,
        *,
        knowledge_document_repository: KnowledgeDocumentRepository,
        outbox_event_repository: OutboxEventRepository,
        automation_execution_repository: AutomationExecutionTasksRepository,
        background_recovery_repository: BackgroundRecoveryRepository | None = None,
        supervisor_repository: SupervisorRepository | None = None,
    ) -> None:
        self.knowledge_document_repository = knowledge_document_repository
        self.outbox_event_repository = outbox_event_repository
        self.automation_execution_repository = automation_execution_repository
        self.background_recovery_repository = background_recovery_repository
        self.supervisor_repository = supervisor_repository

    async def recover(self) -> BackgroundRecoveryResult:
        """执行一轮发件箱租约和文档索引状态补偿。

        功能：恢复超时 ``PROCESSING`` 发件箱事件；扫描已提交但长期未领取的
        ``PENDING`` 文档和心跳中断的 ``PARSING/INDEXING`` 文档；同时分批发现
        Embedding 模型、向量维度或索引版本不兼容的 ``READY`` 文档。

        作用：由周期任务调用，既兜住应用、发布器和索引 Worker 在不同崩溃时间
        点留下的半完成状态，也负责模型切换和索引规则升级后的自动全量重建。

        为什么用它：事务性发件箱提供至少一次发布，但无法单独判断 Worker 是否
        永久消失；数据库时间戳、心跳、有限恢复次数和栅栏任务 ID 组合后，既能
        自动恢复，又能防止无限重试和旧 Worker 覆盖新结果。
        """

        now = utc_now()
        outbox_retried, outbox_failed = await self.outbox_event_repository.recover_stale_processing_events(
            locked_before=now - timedelta(seconds=settings.outbox_processing_timeout_seconds),
            limit=settings.background_recovery_batch_size,
        )

        documents = await self.knowledge_document_repository.lock_stale_index_documents(
            pending_before=now - timedelta(seconds=settings.knowledge_document_pending_timeout_seconds),
            processing_before=now - timedelta(seconds=settings.knowledge_document_processing_timeout_seconds),
            limit=settings.background_recovery_batch_size,
        )
        documents_requeued = 0
        documents_failed = 0
        for document in documents:
            previous_status = document.parse_status
            if document.index_recovery_count >= settings.knowledge_document_max_recoveries:
                document.parse_status = KnowledgeDocumentParseStatus.FAILED.value
                document.error_message = "后台索引任务多次超时，已停止自动恢复，请人工检查后重试"
                document.index_completed_at = now
                documents_failed += 1
                continue

            # 清空旧 Worker 的任务编号就是设置新的栅栏。旧 Worker 后续所有
            # 心跳、状态更新和切片替换都会因 task_id 不匹配而失败。
            document.parse_status = KnowledgeDocumentParseStatus.PENDING.value
            document.error_message = f"系统检测到索引状态 {previous_status} 超时，已自动重新排队"
            document.index_task_id = None
            document.index_queued_at = now
            document.index_started_at = None
            document.index_heartbeat_at = None
            document.index_completed_at = None
            document.index_recovery_count += 1
            self.outbox_event_repository.add_pending_event(
                event_type=OutboxEventType.KNOWLEDGE_DOCUMENT_INDEX.value,
                aggregate_type=OutboxAggregateType.KNOWLEDGE_DOCUMENT.value,
                aggregate_id=document.id,
                payload={"document_id": document.id},
            )
            documents_requeued += 1

        # 两个 Repository 共用同一个 Session；一次提交同时保存本批文档恢复
        # 状态和新发件箱事件，不能在循环中逐条提交。没有记录时回滚只读事务，
        # 及时释放连接和数据库快照。
        if documents:
            await self.knowledge_document_repository.commit()
        else:
            await self.knowledge_document_repository.rollback()

        # 超时恢复与版本重建是两种业务原因，分成两次有限批量查询：前者会增加
        # recovery_count，后者属于正常升级，不应该消耗故障恢复次数。
        rebuild_documents = await self.knowledge_document_repository.lock_documents_requiring_reindex(
            embedding_dimensions=KNOWLEDGE_EMBEDDING_DIMENSIONS,
            index_version=KNOWLEDGE_DOCUMENT_INDEX_VERSION,
            limit=settings.background_recovery_batch_size,
        )
        for document in rebuild_documents:
            document.parse_status = KnowledgeDocumentParseStatus.PENDING.value
            document.error_message = "Embedding 模型、向量维度或索引版本已变化，系统已安排完整重建"
            document.index_task_id = None
            document.index_queued_at = now
            document.index_started_at = None
            document.index_heartbeat_at = None
            document.index_completed_at = None
            document.index_recovery_count = 0
            self.outbox_event_repository.add_pending_event(
                event_type=OutboxEventType.KNOWLEDGE_DOCUMENT_INDEX.value,
                aggregate_type=OutboxAggregateType.KNOWLEDGE_DOCUMENT.value,
                aggregate_id=document.id,
                payload={"document_id": document.id},
            )

        if rebuild_documents:
            await self.knowledge_document_repository.commit()
        else:
            await self.knowledge_document_repository.rollback()

        (
            automation_tasks_timed_out,
            automation_tasks_cancelled,
        ) = await self.automation_execution_repository.finish_stale_tasks(
            now=now,
            grace_seconds=settings.automation_execution_recovery_grace_seconds,
            limit=settings.background_recovery_batch_size,
        )
        requirement_tasks_failed = 0
        case_generation_tasks_failed = 0
        memory_summaries_failed = 0
        tool_tasks_failed = 0
        if self.background_recovery_repository is not None:
            (
                requirement_tasks_failed,
                case_generation_tasks_failed,
                memory_summaries_failed,
                tool_tasks_failed,
            ) = await self.background_recovery_repository.fail_stale_tasks(
                pending_before=now - timedelta(seconds=settings.background_pending_timeout_seconds),
                running_before=now - timedelta(seconds=settings.background_running_timeout_seconds),
                now=now,
                limit=settings.background_recovery_batch_size,
            )

        supervisor_runs_requeued = 0
        supervisor_runs_failed = 0
        if self.supervisor_repository is not None:
            stale_runs = await self.supervisor_repository.lock_stale_running_runs(
                stale_before=now - timedelta(seconds=settings.supervisor_running_timeout_seconds),
                limit=settings.background_recovery_batch_size,
            )
            for run in stale_runs:
                if run.execution_recovery_count >= settings.supervisor_max_recoveries:
                    for step in run.steps:
                        step_status = SupervisorExecutionStepStatus(step.status)
                        if step_status == SupervisorExecutionStepStatus.RUNNING:
                            await self.supervisor_repository.transition_step(
                                run.id,
                                step.id,
                                {step_status},
                                SupervisorExecutionStepStatus.FAILED,
                                error_message="Supervisor Worker 多次失联，已停止自动恢复",
                            )
                        elif step_status == SupervisorExecutionStepStatus.READY:
                            await self.supervisor_repository.transition_step(
                                run.id,
                                step.id,
                                {step_status},
                                SupervisorExecutionStepStatus.SKIPPED,
                                error_message="前序执行多次超时，未继续执行",
                            )
                    await self.supervisor_repository.transition_run(
                        run.project_id,
                        run.id,
                        {SupervisorRunStatus.RUNNING},
                        SupervisorRunStatus.FAILED,
                        error_message="Supervisor Worker 多次失联，已停止自动恢复，请人工检查",
                    )
                    supervisor_runs_failed += 1
                    continue

                has_active_event = await self.outbox_event_repository.has_active_event(
                    event_type=OutboxEventType.SUPERVISOR_EXECUTION.value,
                    aggregate_type=OutboxAggregateType.SUPERVISOR_RUN.value,
                    aggregate_id=run.id,
                )
                if has_active_event:
                    continue
                self.outbox_event_repository.add_pending_event(
                    event_type=OutboxEventType.SUPERVISOR_EXECUTION.value,
                    aggregate_type=OutboxAggregateType.SUPERVISOR_RUN.value,
                    aggregate_id=run.id,
                    payload={"project_id": run.project_id, "run_id": run.id},
                )
                await self.supervisor_repository.mark_running_requeued(run.project_id, run.id)
                supervisor_runs_requeued += 1
            if stale_runs:
                await self.supervisor_repository.commit()
            else:
                await self.supervisor_repository.rollback()

        return BackgroundRecoveryResult(
            outbox_retried=outbox_retried,
            outbox_failed=outbox_failed,
            documents_requeued=documents_requeued,
            documents_failed=documents_failed,
            documents_rebuild_queued=len(rebuild_documents),
            automation_tasks_timed_out=automation_tasks_timed_out,
            automation_tasks_cancelled=automation_tasks_cancelled,
            requirement_tasks_failed=requirement_tasks_failed,
            case_generation_tasks_failed=case_generation_tasks_failed,
            memory_summaries_failed=memory_summaries_failed,
            tool_tasks_failed=tool_tasks_failed,
            supervisor_runs_requeued=supervisor_runs_requeued,
            supervisor_runs_failed=supervisor_runs_failed,
        )
