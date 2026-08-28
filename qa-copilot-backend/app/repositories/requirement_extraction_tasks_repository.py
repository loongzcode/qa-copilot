"""需求拆解任务的数据访问层。

本 Repository 只负责拼接 SQL 并返回 ORM 实体，不负责项目权限、模型调用或
Prompt 拼装；这些业务判断统一放在 Service 中。
"""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.constants import RequirementExtractionStage, RequirementExtractionTaskStatus
from app.models import RequirementExtractionTask
from app.models.mixins import utc_now
from app.repositories.base_repository import BaseRepository


class RequirementExtractionTasksRepository(BaseRepository):
    """读写 requirement_extraction_tasks 表。"""

    async def get_active_task(
            self,
            requirement_id: int,
    ) -> RequirementExtractionTask | None:
        """查询需求当前是否已有排队中或执行中的任务。

        Service 在创建新任务前调用本方法，避免同一需求被重复拆解。数据库还有
        部分唯一索引作最后保护；这里提前查询是为了返回容易理解的业务错误。
        """
        statement = (
            select(RequirementExtractionTask)
            # Mapper 返回 requested_by_name 时需要访问 requester，提前加载可避免
            # 实体离开异步查询上下文后再次隐式访问数据库。
            .options(selectinload(RequirementExtractionTask.requester))
            .where(
                RequirementExtractionTask.requirement_id == requirement_id,
                RequirementExtractionTask.status.in_(
                    (
                        RequirementExtractionTaskStatus.PENDING.value,
                        RequirementExtractionTaskStatus.RUNNING.value,
                    )
                ),
            )
            # 理论上部分唯一索引保证最多只有一条；排序仍能让旧数据异常时
            # 优先返回最近创建的任务。
            .order_by(
                RequirementExtractionTask.created_at.desc(),
                RequirementExtractionTask.id.desc(),
            )
        )
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def get_latest_task(
            self,
            project_id: int,
            requirement_id: int,
    ) -> RequirementExtractionTask | None:
        """查询某个项目中某个需求最近创建的一条拆解任务。

        前端刷新页面后用它恢复最新进度，所以无论任务成功、失败还是仍在执行，
        都应参与查询，不能只筛选活动状态。
        """
        statement = (
            select(RequirementExtractionTask)
            .options(selectinload(RequirementExtractionTask.requester))
            .where(
                RequirementExtractionTask.project_id == project_id,
                RequirementExtractionTask.requirement_id == requirement_id,
            )
            # created_at 相同的极端情况下，再用递增主键 id 确定谁更新。
            .order_by(
                RequirementExtractionTask.created_at.desc(),
                RequirementExtractionTask.id.desc(),
            )
        )
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def get_task(
            self,
            project_id: int,
            requirement_id: int,
            task_id: int,
            *,
            lock:bool = False
    ) -> RequirementExtractionTask | None:
        """使用项目、需求和任务三个 ID 精确查询，防止跨项目读取。

        虽然 task_id 是主键，仅按它查询也能找到记录，但同时限制项目和需求后，
        用户即使猜到其他项目的任务 ID，也无法读取其输入输出快照。
        """
        statement = (
            select(RequirementExtractionTask)
            .options(selectinload(RequirementExtractionTask.requester))
            .where(
                RequirementExtractionTask.id == task_id,
                RequirementExtractionTask.project_id == project_id,
                RequirementExtractionTask.requirement_id == requirement_id,
            )
        )
        if lock:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        # 三个等值条件中包含主键 id，因此最多返回一条。
        return result.scalar_one_or_none()

    async def claim_task(
            self,
            extraction_task_id: int,
            celery_task_id: str,
    ) -> RequirementExtractionTask | None:
        statement = (
            select(RequirementExtractionTask)
            .options(selectinload(RequirementExtractionTask.requester))
            .where(
                RequirementExtractionTask.id == extraction_task_id,
                RequirementExtractionTask.celery_task_id == celery_task_id,
                RequirementExtractionTask.status == RequirementExtractionTaskStatus.PENDING.value
            )
            .with_for_update()
        )
        task = await self.session.scalar(statement)
        if task is None:
            await self.rollback()
            return None
        task.status = RequirementExtractionTaskStatus.RUNNING.value
        task.current_stage = RequirementExtractionStage.LOADING_DOCUMENT.value
        task.progress = 5
        task.started_at = utc_now()
        task.error_message = None
        await self.commit()
        return task
