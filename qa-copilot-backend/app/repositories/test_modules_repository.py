from sqlalchemy import select

from app.models import TestModule
from app.repositories.base_repository import BaseRepository


class TestModulesRepository(BaseRepository):
    async def list_modules(
        self,
        project_id: int,
    ) -> list[TestModule]:
        # 创建查询 TestModule 的 select 语句
        statement = (
            select(TestModule)
            # 添加 project_id 查询条件
            .where(TestModule.project_id == project_id)
            # 先按照 order_no 排序，相同顺序再按照 id 排序
            .order_by(TestModule.order_no, TestModule.id)
        )
        # 使用 session.scalars() 执行查询
        # 使用 all() 取出全部实体
        # 转换成普通 list 返回
        return list((await self.session.scalars(statement)).all())

    async def get_module(
        self,
        project_id: int,
        module_id: int,
    ) -> TestModule | None:
        # 创建查询 TestModule 的 select 语句
        statement = (
            select(TestModule)
            # 添加项目 ID 条件
            # 添加模块 ID 条件
            .where(TestModule.project_id == project_id)
            .where(TestModule.id == module_id)
        )
        # 执行查询并返回一个实体或 None
        result = await self.session.scalar(statement)
        return result

    async def is_descendant(
        self,
        project_id: int,
        ancestor_id: int,
        descendant_id: int,
    ) -> bool:
        # 从 descendant_id 开始向上查找
        current_id: int | None = descendant_id
        # 创建集合，记录已经检查过的模块，避免异常数据造成死循环
        visited_ids: set[int] = set()
        # 只要当前模块 ID 不为空，就继续循环
        while current_id is not None:
            if current_id in visited_ids:
                return True
            # 记录当前模块已经检查过。
            visited_ids.add(current_id)
            # 找到了 ancestor_id，说明 descendant_id 位于它的子树中。
            if current_id == ancestor_id:
                return True
            # 查询当前模块，获取它的 parent_id。
            current_module = await self.get_module(
                project_id,
                current_id,
            )
            # 模块不存在，无法继续向上查找。
            if current_module is None:
                return False
            # 向上移动一层。
            current_id = current_module.parent_id
        # 已经走到一级模块之上，仍然没有找到 ancestor_id。
        return False
