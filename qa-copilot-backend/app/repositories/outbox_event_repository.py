from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from app.core.constants import OutboxEventStatus
from app.models import OutboxEvent
from app.models.mixins import utc_now
from app.repositories.base_repository import BaseRepository


class OutboxEventRepository(BaseRepository):
    """负责事务性发件箱事件的持久化操作。"""

    def add_pending_event(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: int,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        """创建一条尚未发布的发件箱事件并加入当前数据库会话。

        功能：把任务类型、业务对象和 Celery 参数快照封装成 ``PENDING``
        发件箱实体。

        作用：由业务 Service 在修改业务对象时调用；本方法只执行 ``add``，
        不自行提交，使事件可以和业务状态共用同一个事务。

        为什么用它：如果 Repository 在这里立即 ``commit``，文档状态与事件又
        会被拆成两个事务。把最终提交权留给 Service，可以清晰地划定事务边界。
        """

        event = OutboxEvent(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            status=OutboxEventStatus.PENDING.value,
        )
        self.add(event)
        return event

    async def has_active_event(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: int,
    ) -> bool:
        """判断同一业务对象是否已有待发布、发布中或待重试事件。"""
        event_id = await self.session.scalar(
            select(OutboxEvent.id)
            .where(
                OutboxEvent.event_type == event_type,
                OutboxEvent.aggregate_type == aggregate_type,
                OutboxEvent.aggregate_id == aggregate_id,
                OutboxEvent.status.in_(
                    (
                        OutboxEventStatus.PENDING.value,
                        OutboxEventStatus.PROCESSING.value,
                        OutboxEventStatus.RETRY.value,
                    )
                ),
            )
            .limit(1)
        )
        return event_id is not None

    async def count_active_events_by_type_and_status(
        self,
    ) -> list[tuple[str, str, int]]:
        """统计当前等待、重试和发布中的发件箱事件。

        功能：按事件类型和状态聚合活动记录数量。

        作用：由周期发件箱 Worker 刷新 Prometheus 队列积压 Gauge；不参与消息
        认领和状态修改。

        为什么用它：PostgreSQL 是事务性发件箱的事实来源，从数据库聚合比在
        进程内对发布动作加减计数更可靠，Worker 重启后也不会丢失积压量。
        """

        statement = (
            select(
                OutboxEvent.event_type,
                OutboxEvent.status,
                func.count(OutboxEvent.id),
            )
            .where(
                OutboxEvent.status.in_(
                    (
                        OutboxEventStatus.PENDING.value,
                        OutboxEventStatus.PROCESSING.value,
                        OutboxEventStatus.RETRY.value,
                    )
                )
            )
            .group_by(OutboxEvent.event_type, OutboxEvent.status)
        )
        rows = (await self.session.execute(statement)).all()
        return [
            (str(event_type), str(status), int(count))
            for event_type, status, count in rows
        ]

    async def claim_available_events(
        self,
        *,
        locked_by: str,
        limit: int,
    ) -> list[OutboxEvent]:
        """安全认领一批已经到达发送时间的发件箱事件。

        功能：查询 ``PENDING`` 或 ``RETRY`` 且 ``available_at`` 已到期的事件，
        使用行锁跳过其他发布器正在处理的记录，并推进到 ``PROCESSING``。

        作用：发件箱发布器每轮首先调用本方法，取得本实例独占处理的一批事件。

        为什么用它：``FOR UPDATE SKIP LOCKED`` 允许多个发布器并行领取不同记录，
        无需全局锁；先提交 ``PROCESSING`` 可留下明确恢复点，进程崩溃后由后续
        补偿扫描恢复超时事件。
        """

        now = utc_now()
        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status.in_(
                    (
                        OutboxEventStatus.PENDING.value,
                        OutboxEventStatus.RETRY.value,
                    )
                ),
                OutboxEvent.available_at <= now,
            )
            .order_by(OutboxEvent.available_at, OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = list((await self.session.scalars(statement)).all())
        if not events:
            # SELECT 已开启隐式事务；无数据时回滚可立即释放连接和事务快照。
            await self.rollback()
            return []

        for event in events:
            event.status = OutboxEventStatus.PROCESSING.value
            event.locked_at = now
            event.locked_by = locked_by
            event.last_error = None

        await self.commit()
        return events

    async def mark_published(
        self,
        event_id: int,
        broker_task_id: str,
    ) -> bool:
        """把成功写入 Redis 的事件标记为已发布。

        功能：锁定指定 ``PROCESSING`` 事件，增加尝试次数，保存 Celery 任务 ID
        和发布时间，并清空认领信息。

        作用：发布器在 ``send_task`` 成功返回后调用，形成可审计的发布终态。

        为什么用它：只允许 ``PROCESSING`` 状态推进，避免过期发布器覆盖已经被
        补偿流程处理的新状态；单行事务也让计数和状态同步变化。
        """

        event = await self._get_processing_event(event_id)
        if event is None:
            await self.rollback()
            return False

        event.status = OutboxEventStatus.PUBLISHED.value
        event.attempt_count += 1
        event.published_at = utc_now()
        event.broker_task_id = broker_task_id
        event.locked_at = None
        event.locked_by = None
        event.last_error = None
        await self.commit()
        return True

    async def mark_publish_failure(
        self,
        event_id: int,
        *,
        error_message: str,
        retry_delay_seconds: int,
        permanent: bool = False,
    ) -> str | None:
        """记录发布失败，并决定延迟重试还是进入最终失败。

        功能：增加尝试次数；永久错误或次数耗尽时标记 ``FAILED``，否则标记
        ``RETRY`` 并计算下一次 ``available_at``。

        作用：统一处理 Redis 临时不可用、网络故障和不受支持事件等失败分支。

        为什么用它：把状态判断放在持有行锁的事务内，可以避免两个发布器同时
        修改尝试次数；数据库时间点使重试在进程重启后仍然有效。
        """

        event = await self._get_processing_event(event_id)
        if event is None:
            await self.rollback()
            return None

        event.attempt_count += 1
        attempts_exhausted = event.attempt_count >= event.max_attempts
        event.status = (
            OutboxEventStatus.FAILED.value
            if permanent or attempts_exhausted
            else OutboxEventStatus.RETRY.value
        )
        event.available_at = utc_now() + timedelta(seconds=retry_delay_seconds)
        event.locked_at = None
        event.locked_by = None
        event.last_error = error_message[:4000]
        await self.commit()
        return event.status

    async def _get_processing_event(
        self,
        event_id: int,
    ) -> OutboxEvent | None:
        """锁定并返回仍处于发布中的单条事件。

        功能：按主键和 ``PROCESSING`` 状态查询事件并获取数据库行锁。

        作用：供发布成功和失败两个状态更新方法复用相同的并发保护条件。

        为什么用它：集中查询条件可以防止两个终态方法的状态限制逐渐不一致；
        行锁保证读取尝试次数后到提交前不会被另一事务同时修改。
        """

        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.id == event_id,
                OutboxEvent.status == OutboxEventStatus.PROCESSING.value,
            )
            .with_for_update()
        )
        return await self.session.scalar(statement)

    async def recover_stale_processing_events(
        self,
        *,
        locked_before: datetime,
        limit: int,
    ) -> tuple[int, int]:
        """恢复发布器退出后长期停留在 PROCESSING 的事件。

        功能：锁定认领时间早于阈值的事件，增加尝试次数；仍可尝试的事件转为
        ``RETRY``，耗尽次数的事件转为 ``FAILED``。

        作用：修复消息可能已发送、但发布器尚未保存 ``PUBLISHED`` 就退出的
        崩溃窗口，后续允许至少一次重新投递。

        为什么用它：Redis 与 PostgreSQL 无法组成一个本地事务，发送后崩溃无法
        完全消除；超时租约加消费者幂等是事务性发件箱常见的恢复方案。
        """

        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == OutboxEventStatus.PROCESSING.value,
                OutboxEvent.locked_at.is_not(None),
                OutboxEvent.locked_at <= locked_before,
            )
            .order_by(OutboxEvent.locked_at, OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = list((await self.session.scalars(statement)).all())
        if not events:
            await self.rollback()
            return 0, 0

        retry_count = 0
        failed_count = 0
        now = utc_now()
        for event in events:
            event.attempt_count += 1
            if event.attempt_count >= event.max_attempts:
                event.status = OutboxEventStatus.FAILED.value
                failed_count += 1
            else:
                event.status = OutboxEventStatus.RETRY.value
                event.available_at = now
                retry_count += 1
            event.locked_at = None
            event.locked_by = None
            event.last_error = "发布器处理超时，系统已执行补偿恢复"

        await self.commit()
        return retry_count, failed_count
