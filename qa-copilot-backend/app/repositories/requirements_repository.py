from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload, with_expression
from sqlalchemy.sql.functions import func

from app.core.constants import RequirementStatus
from app.models import Requirement, RequirementItem
from app.repositories.base_repository import BaseRepository


class RequirementsRepository(BaseRepository):
    """需求与原子需求点的数据访问层。

    这里暂时只建立 Repository 类型。接下来从 API 定义第一个接口后，
    再根据那个接口真正需要的数据，逐步补充查询方法，避免提前写出无人调用的方法。
    """

    async def list_requirements(
            self,
            project_id: int,
            keyword: str,
            status: RequirementStatus | None,
            current: int,
            size: int,
    ):
        condition = [
            Requirement.project_id == project_id,
            Requirement.deleted_at.is_(None)
        ]
        if keyword:
            condition.append(
                or_(
                    Requirement.title.contains(keyword),
                    Requirement.source_url.contains(keyword)
                )
            )
        if status is not None:
            condition.append(
                Requirement.status == status.value
            )

        item_count_expression = (
            select(func.count(RequirementItem.id))
            .where(RequirementItem.requirement_id == Requirement.id)
            .correlate(Requirement)
            .scalar_subquery()
        )
        confirmed_item_count_expression = (
            select(func.count(RequirementItem.id))
            .where(RequirementItem.requirement_id == Requirement.id)
            .where(RequirementItem.confirmed.is_(True))
            .correlate(Requirement)
            .scalar_subquery()
        )
        query = (
            select(Requirement)
            .options(
                selectinload(Requirement.module),
                selectinload(Requirement.document),
                selectinload(Requirement.creator),
                with_expression(Requirement.item_count, item_count_expression),
                with_expression(
                    Requirement.confirmed_item_count,
                    confirmed_item_count_expression,
                )
            )
            .where(*condition)
            .order_by(Requirement.updated_at.desc(), Requirement.id.desc())
            .offset((current - 1) * size)
            .limit(size)
        )
        total_query = (
            select(func.count(Requirement.id))
            .where(*condition)
        )
        total = await self.session.scalar(total_query)
        result = await self.session.scalars(query)
        records = list(result.all())

        return records, int(total or 0)

    async def get_requirement_detail(
            self,
            project_id: int,
            requirement_id: int,
            *,
            lock: bool = False,
    ) -> Requirement | None:
        """查询需求详情；写操作可使用行锁避免并发覆盖需求状态。"""
        condition = [
            Requirement.project_id == project_id,
            Requirement.id == requirement_id,
            Requirement.deleted_at.is_(None)
        ]
        item_count_expression = (
            select(func.count(RequirementItem.id))
            .where(RequirementItem.requirement_id == Requirement.id)
            .correlate(Requirement)
            .scalar_subquery()
        )
        confirmed_item_count_expression = (
            select(func.count(RequirementItem.id))
            .where(RequirementItem.requirement_id == Requirement.id)
            .where(RequirementItem.confirmed.is_(True))
            .correlate(Requirement)
            .scalar_subquery()
        )
        statement = (
            select(Requirement)
            .options(
                selectinload(Requirement.module),
                selectinload(Requirement.document),
                selectinload(Requirement.creator),
                selectinload(Requirement.items),
                with_expression(Requirement.item_count, item_count_expression),
                with_expression(
                    Requirement.confirmed_item_count,
                    confirmed_item_count_expression,
                )
            )
            .where(*condition)
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

