from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.constants import OutboxEventType
from app.core.metrics import record_outbox_publish_result
from app.models import OutboxEvent
from app.repositories.outbox_event_repository import OutboxEventRepository

logger = logging.getLogger(__name__)


class UnsupportedOutboxEventError(ValueError):
    """表示事件类型或参数不在发布器允许的固定白名单中。"""


@dataclass(frozen=True, slots=True)
class OutboxPublishBatchResult:
    """一轮发件箱发布的统计结果。"""

    claimed: int
    published: int
    retry_scheduled: int
    failed: int


@dataclass(frozen=True, slots=True)
class CeleryMessage:
    """由受控发件箱事件转换出的 Celery 消息参数。"""

    task_name: str
    args: list[Any]
    kwargs: dict[str, Any]


class OutboxEventService:
    """认领发件箱事件并可靠发布到 Celery Broker。"""

    def __init__(self, repository: OutboxEventRepository) -> None:
        self.repository = repository

    async def publish_batch(
        self,
        *,
        publisher_id: str,
        batch_size: int | None = None,
    ) -> OutboxPublishBatchResult:
        """认领并发布一批到期的发件箱事件。

        功能：从数据库认领事件，按固定白名单构造 Celery 消息，成功时保存
        ``PUBLISHED``，失败时安排指数退避重试或进入 ``FAILED``。

        作用：由周期性 Celery 任务调用，是 PostgreSQL 发件箱与 Redis 队列之间
        唯一允许的消息出口。

        为什么用它：批量认领减少定时轮询开销，逐条发布和逐条记录终态可避免
        一条坏消息阻塞整批；固定映射禁止数据库内容任意指定可执行任务。
        """

        effective_batch_size = batch_size or settings.outbox_publish_batch_size
        events = await self.repository.claim_available_events(
            locked_by=publisher_id,
            limit=effective_batch_size,
        )

        published = 0
        retry_scheduled = 0
        failed = 0

        for event in events:
            try:
                message = self._build_celery_message(event)
                broker_task_id = f"outbox-{event.id}"
                await asyncio.to_thread(
                    celery_app.send_task,
                    message.task_name,
                    args=message.args,
                    kwargs=message.kwargs,
                    task_id=broker_task_id,
                    retry=False,
                )
                state_saved = await self.repository.mark_published(
                    event.id,
                    broker_task_id,
                )
                if state_saved:
                    published += 1
                    record_outbox_publish_result(
                        event_type=event.event_type,
                        result="published",
                    )
                else:
                    # 消息已进入 Redis，但数据库事件不再处于 PROCESSING。
                    # 消费者仍以文档状态和行锁保证幂等，这里保留告警供审计。
                    failed += 1
                    record_outbox_publish_result(
                        event_type=event.event_type,
                        result="state_conflict",
                    )
                    logger.warning(
                        "发件箱事件发布成功但终态未保存：event_id=%s task_id=%s",
                        event.id,
                        broker_task_id,
                    )
            except UnsupportedOutboxEventError as exc:
                await self.repository.mark_publish_failure(
                    event.id,
                    error_message=str(exc),
                    retry_delay_seconds=0,
                    permanent=True,
                )
                failed += 1
                record_outbox_publish_result(
                    event_type=event.event_type,
                    result="failed",
                )
            except Exception as exc:
                retry_delay = self._retry_delay_seconds(event.attempt_count)
                next_status = await self.repository.mark_publish_failure(
                    event.id,
                    error_message=(
                        f"{type(exc).__name__}: Celery 消息发布失败"
                    ),
                    retry_delay_seconds=retry_delay,
                )
                if next_status == "RETRY":
                    retry_scheduled += 1
                    record_outbox_publish_result(
                        event_type=event.event_type,
                        result="retry",
                    )
                else:
                    failed += 1
                    record_outbox_publish_result(
                        event_type=event.event_type,
                        result="failed",
                    )
                logger.warning(
                    "发件箱事件发布失败：event_id=%s error_type=%s next_status=%s",
                    event.id,
                    type(exc).__name__,
                    next_status,
                )

        return OutboxPublishBatchResult(
            claimed=len(events),
            published=published,
            retry_scheduled=retry_scheduled,
            failed=failed,
        )

    @staticmethod
    def _build_celery_message(event: OutboxEvent) -> CeleryMessage:
        """把白名单中的业务事件转换成 Celery 任务名称与参数。

        功能：校验事件类型和 ``payload``，生成受控的任务调用描述。

        作用：隔离数据库事件结构与 Celery API；以后新增事件时必须在这里显式
        注册映射，而不是信任数据库提供的任意任务名称。

        为什么用它：发件箱内容属于数据，不能直接变成可执行指令。固定白名单
        能降低数据被篡改后触发任意后台任务的安全风险。
        """

        if event.event_type == OutboxEventType.KNOWLEDGE_DOCUMENT_INDEX.value:
            document_id = event.payload.get("document_id")
            if (
                isinstance(document_id, bool)
                or not isinstance(document_id, int)
                or document_id <= 0
            ):
                raise UnsupportedOutboxEventError(
                    "知识文档索引事件缺少合法的 document_id"
                )
            return CeleryMessage(
                task_name="knowledge.index_document",
                args=[document_id],
                kwargs={},
            )

        if (
            event.event_type
            == OutboxEventType.KNOWLEDGE_DOCUMENT_FILE_DELETE.value
        ):
            document_id = event.payload.get("document_id")
            object_key = event.payload.get("object_key")
            if (
                isinstance(document_id, bool)
                or not isinstance(document_id, int)
                or document_id <= 0
            ):
                raise UnsupportedOutboxEventError(
                    "知识文档文件删除事件缺少合法的 document_id"
                )
            if (
                not isinstance(object_key, str)
                or not object_key.strip()
                or len(object_key) > 1000
            ):
                raise UnsupportedOutboxEventError(
                    "知识文档文件删除事件缺少合法的 object_key"
                )
            return CeleryMessage(
                task_name="knowledge.delete_document_file",
                args=[document_id, object_key],
                kwargs={},
            )

        if event.event_type == OutboxEventType.AUTOMATION_EXECUTION.value:
            project_id = event.payload.get("project_id")
            execution_task_id = event.payload.get("execution_task_id")
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
                for value in (project_id, execution_task_id)
            ):
                raise UnsupportedOutboxEventError("自动化执行事件缺少合法的项目或任务 ID")
            return CeleryMessage(
                task_name="automation.execute",
                args=[project_id, execution_task_id],
                kwargs={},
            )

        if (
            event.event_type
            == OutboxEventType.AUTOMATION_RESULT_NOTIFICATION.value
        ):
            project_id = event.payload.get("project_id")
            execution_task_id = event.payload.get("execution_task_id")
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
                for value in (project_id, execution_task_id)
            ):
                raise UnsupportedOutboxEventError(
                    "自动化结果通知事件缺少合法的项目或任务 ID"
                )
            return CeleryMessage(
                task_name="notification.send_automation_result",
                args=[project_id, execution_task_id],
                kwargs={},
            )

        if event.event_type == OutboxEventType.SUPERVISOR_EXECUTION.value:
            project_id = event.payload.get("project_id")
            run_id = event.payload.get("run_id")
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
                for value in (project_id, run_id)
            ):
                raise UnsupportedOutboxEventError("Supervisor 执行事件缺少合法的项目或运行 ID")
            return CeleryMessage(
                task_name="supervisor.execute_run",
                args=[project_id, run_id],
                kwargs={},
            )

        raise UnsupportedOutboxEventError(
            f"不支持的发件箱事件类型：{event.event_type}"
        )

    @staticmethod
    def _retry_delay_seconds(previous_attempt_count: int) -> int:
        """计算下一次发布的指数退避秒数。

        功能：第一次失败等待基础秒数，之后每失败一次等待时间翻倍，并受最大值
        限制。

        作用：供临时 Redis 或网络异常分支计算 ``available_at``。

        为什么用它：立即高频重试会在依赖故障时持续施压；指数退避能逐步降低
        请求频率，最大值又能避免等待时间无限增长。
        """

        multiplier = 2 ** min(previous_attempt_count, 10)
        return min(
            settings.outbox_retry_base_seconds * multiplier,
            settings.outbox_retry_max_seconds,
        )
