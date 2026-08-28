"""原子需求点的数据访问层。

Repository 只负责生成和执行数据库查询，不判断当前用户是否有项目权限，也不决定
需求是否允许编辑；这些业务规则统一放在 RequirementItemsService 中。
"""

from sqlalchemy import delete, func, select

from app.models import RequirementItem
from app.repositories.base_repository import BaseRepository


class RequirementItemsRepository(BaseRepository):
    """封装需求点 CRUD、层级和确认统计所需的数据库操作。"""

    async def get_item(
        self,
        requirement_id: int,
        item_id: int,
        *,
        lock: bool = False,
    ) -> RequirementItem | None:
        """按需求范围查询一条需求点，防止通过 item_id 越权访问其他需求。"""

        statement = select(RequirementItem).where(
            RequirementItem.requirement_id == requirement_id,
            RequirementItem.id == item_id,
        )
        # 编辑、删除和确认时锁定目标行，避免两个请求同时覆盖同一条数据。
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_items_by_ids(
        self,
        requirement_id: int,
        item_ids: list[int],
        *,
        lock: bool = False,
    ) -> list[RequirementItem]:
        """一次查询并可锁定批量确认的需求点，避免前端循环访问数据库。"""

        if not item_ids:
            return []
        statement = select(RequirementItem).where(
            RequirementItem.requirement_id == requirement_id,
            RequirementItem.id.in_(item_ids),
        )
        if lock:
            statement = statement.with_for_update()
        return list((await self.session.scalars(statement)).all())

    async def list_items_for_update(
        self,
        requirement_id: int,
    ) -> list[RequirementItem]:
        """查询并锁定一份需求当前的全部需求点。

        功能：按显示顺序返回指定需求的所有需求点，并对查询到的行添加更新锁。
        作用：需求重新拆解前，执行 Service 使用完整列表识别可替换的 AI 需求点、
        保留人工或已确认节点，并安全调整仍需保留的父子关系。
        为什么用它：替换层级数据必须在同一份稳定快照上计算；``FOR UPDATE`` 能
        防止人工确认、编辑和 AI 替换同时覆盖。相比循环按 ID 查询，一次查询可
        避免 N+1 SQL，并让 Service 在内存中完成树关系判断。
        """

        statement = (
            select(RequirementItem)
            .where(RequirementItem.requirement_id == requirement_id)
            .order_by(
                RequirementItem.order_no,
                RequirementItem.id,
            )
            .with_for_update()
        )
        return list((await self.session.scalars(statement)).all())

    async def delete_items_by_ids(
        self,
        requirement_id: int,
        item_ids: set[int],
    ) -> None:
        """批量删除一份需求中指定的需求点。

        功能：使用 requirement_id 和 ID 集合双重限定，一条 SQL 删除已由 Service
        判定可替换的需求点；空集合时不访问数据库。
        作用：在 Service 先解除保留节点对待删除父级的引用后，完成旧 AI 结果清理，
        为同一事务内写入新一批需求点腾出空间。
        为什么用它：批量 DELETE 比逐个 ``session.delete`` 往返更少，也能避免删除
        父节点触发数据库级联后，ORM 再重复删除其子节点。requirement_id 条件是额外
        的数据边界，即使调用方传错 ID，也不会删除其他需求的数据。
        """

        if not item_ids:
            return
        statement = delete(RequirementItem).where(
            RequirementItem.requirement_id == requirement_id,
            RequirementItem.id.in_(item_ids),
        )
        await self.session.execute(statement)

    async def get_item_by_code(
        self,
        requirement_id: int,
        item_code: str,
        *,
        exclude_item_id: int | None = None,
    ) -> RequirementItem | None:
        """查询同一需求中是否已有相同编码；编辑时可排除当前需求点。"""

        conditions = [
            RequirementItem.requirement_id == requirement_id,
            RequirementItem.item_code == item_code,
        ]
        if exclude_item_id is not None:
            conditions.append(RequirementItem.id != exclude_item_id)
        return await self.session.scalar(select(RequirementItem).where(*conditions))

    async def has_children(self, requirement_id: int, item_id: int) -> bool:
        """判断需求点是否仍有直接子节点，删除前用于避免意外级联删除整棵子树。"""

        child_count = await self.session.scalar(
            select(func.count(RequirementItem.id)).where(
                RequirementItem.requirement_id == requirement_id,
                RequirementItem.parent_id == item_id,
            )
        )
        return bool(child_count)

    async def count_items(self, requirement_id: int) -> int:
        """统计需求当前剩余的需求点数量。"""

        count = await self.session.scalar(
            select(func.count(RequirementItem.id)).where(
                RequirementItem.requirement_id == requirement_id
            )
        )
        return int(count or 0)

    async def count_unconfirmed_items(self, requirement_id: int) -> int:
        """统计尚未人工确认的需求点，用于判断需求能否进入 CONFIRMED。"""

        count = await self.session.scalar(
            select(func.count(RequirementItem.id)).where(
                RequirementItem.requirement_id == requirement_id,
                RequirementItem.confirmed.is_(False),
            )
        )
        return int(count or 0)
