"""事务性发件箱到 Redis/Celery 的本地集成冒烟测试。"""

import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.celery_app import celery_app  # noqa: E402
from app.core.constants import OutboxAggregateType, OutboxEventType  # noqa: E402
from app.core.database import AsyncSessionFactory, engine  # noqa: E402
from app.models import OutboxEvent  # noqa: E402
from app.models.mixins import utc_now  # noqa: E402


async def main() -> None:
    """创建测试事件、触发发布、等待终态并清理测试数据。"""

    # 使用 PostgreSQL INTEGER 范围内且极不可能存在的文档 ID。即使知识索引
    # Worker 收到消息，也只会查询不到文档后返回 False，不会调用模型。
    fake_document_id = 2_000_000_000
    event_id: int | None = None

    try:
        async with AsyncSessionFactory() as session:
            event = OutboxEvent(
                event_type=OutboxEventType.KNOWLEDGE_DOCUMENT_INDEX.value,
                aggregate_type=OutboxAggregateType.KNOWLEDGE_DOCUMENT.value,
                aggregate_id=fake_document_id,
                payload={"document_id": fake_document_id},
            )
            session.add(event)
            await session.commit()
            event_id = event.id

        await asyncio.to_thread(
            celery_app.send_task,
            "system.publish_outbox",
            task_id=f"outbox-smoke-trigger-{uuid4().hex}",
            retry=False,
        )

        deadline = utc_now() + timedelta(seconds=20)
        while utc_now() < deadline:
            async with AsyncSessionFactory() as session:
                current = await session.scalar(
                    select(OutboxEvent).where(OutboxEvent.id == event_id)
                )
                if current is not None and current.status == "PUBLISHED":
                    print(
                        "Outbox smoke passed:",
                        current.id,
                        current.status,
                        current.broker_task_id,
                    )
                    return
                if current is not None and current.status == "FAILED":
                    raise RuntimeError(
                        f"发件箱事件进入 FAILED：{current.last_error}"
                    )
            await asyncio.sleep(0.5)

        raise TimeoutError("20 秒内未观察到发件箱事件 PUBLISHED")
    finally:
        if event_id is not None:
            async with AsyncSessionFactory() as session:
                await session.execute(
                    delete(OutboxEvent).where(OutboxEvent.id == event_id)
                )
                await session.commit()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
