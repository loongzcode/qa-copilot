"""跨业务后台任务的超时收口查询。"""

from datetime import datetime

from sqlalchemy import select

from app.core.constants import (
    CaseGenerationTaskStatus,
    KnowledgeChatMemoryStatus,
    RequirementExtractionTaskStatus,
    ToolTaskStatus,
)
from app.models import (
    CaseGenerationTask,
    KnowledgeChatMemorySummary,
    RequirementExtractionTask,
    ToolExecutionLog,
    ToolTask,
)
from app.repositories.base_repository import BaseRepository


class BackgroundRecoveryRepository(BaseRepository):
    """锁定并收口无法再由原 Worker 正常完成的后台记录。

    功能：分批查找长期排队或运行的需求拆解、用例生成、记忆压缩和工具任务。
    作用：供 Celery Beat 周期恢复任务统一调用，释放活动任务唯一约束并给页面明确终态。
    为什么用它：这些旧表没有统一心跳和重试计数字段，盲目重新入队可能造成重复
    AI 调用或外部写操作；当前先安全标记失败，用户可从业务页面明确重试。
    """

    async def fail_stale_tasks(
        self,
        *,
        pending_before: datetime,
        running_before: datetime,
        now: datetime,
        limit: int,
    ) -> tuple[int, int, int, int]:
        requirement_tasks = list(
            (
                await self.session.scalars(
                    select(RequirementExtractionTask)
                    .where(
                        (
                            (RequirementExtractionTask.status == RequirementExtractionTaskStatus.PENDING.value)
                            & (RequirementExtractionTask.updated_at < pending_before)
                        )
                        | (
                            (RequirementExtractionTask.status == RequirementExtractionTaskStatus.RUNNING.value)
                            & (RequirementExtractionTask.updated_at < running_before)
                        )
                    )
                    .order_by(RequirementExtractionTask.updated_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for task in requirement_tasks:
            task.status = RequirementExtractionTaskStatus.FAILED.value
            task.current_stage = "FAILED"
            task.error_message = "后台任务长时间无进展，系统已安全终止，请重新提交拆解"
            task.finished_at = now

        case_tasks = list(
            (
                await self.session.scalars(
                    select(CaseGenerationTask)
                    .where(
                        (
                            (CaseGenerationTask.status == CaseGenerationTaskStatus.PENDING.value)
                            & (CaseGenerationTask.updated_at < pending_before)
                        )
                        | (
                            (CaseGenerationTask.status == CaseGenerationTaskStatus.RUNNING.value)
                            & (CaseGenerationTask.updated_at < running_before)
                        )
                    )
                    .order_by(CaseGenerationTask.updated_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for task in case_tasks:
            task.status = CaseGenerationTaskStatus.FAILED.value
            task.current_stage = "FAILED"
            task.error_message = "后台任务长时间无进展，系统已安全终止，请重新生成"
            task.finished_at = now

        memory_summaries = list(
            (
                await self.session.scalars(
                    select(KnowledgeChatMemorySummary)
                    .where(
                        KnowledgeChatMemorySummary.status == KnowledgeChatMemoryStatus.PENDING.value,
                        KnowledgeChatMemorySummary.updated_at < running_before,
                    )
                    .order_by(KnowledgeChatMemorySummary.updated_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for summary in memory_summaries:
            summary.status = KnowledgeChatMemoryStatus.FAILED.value
            summary.error_message = "记忆压缩长时间未完成，已标记失败；原始消息不受影响"

        tool_tasks = list(
            (
                await self.session.scalars(
                    select(ToolTask)
                    .where(
                        ToolTask.status == ToolTaskStatus.RUNNING.value,
                        ToolTask.updated_at < running_before,
                    )
                    .order_by(ToolTask.updated_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for task in tool_tasks:
            task.status = ToolTaskStatus.FAILED.value
            task.error_message = "工具任务长时间无进展，已停止；外部写操作请先人工核对后再重试"
            task.finished_at = now
            self.add(
                ToolExecutionLog(
                    task_id=task.id,
                    stage="RECOVERY",
                    level="ERROR",
                    message=task.error_message,
                    details={"reason": "STALE_RUNNING_TASK"},
                )
            )

        if requirement_tasks or case_tasks or memory_summaries or tool_tasks:
            await self.commit()
        else:
            await self.rollback()
        return (
            len(requirement_tasks),
            len(case_tasks),
            len(memory_summaries),
            len(tool_tasks),
        )
