"""自动化定义的数据访问层。"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.core.constants import AutomationDefinitionStatus
from app.models import AutomationDefinition, AutomationDefinitionChange, TestCase
from app.repositories.base_repository import BaseRepository


class AutomationDefinitionsRepository(BaseRepository):
    """封装自动化定义查询、版本号计算和状态更新。

    功能：集中处理定义列表、详情、版本和审批时需要的数据库操作。
    作用：Service 只表达业务状态机，不直接拼接 SQLAlchemy 查询。
    为什么用它：审批需要行锁和部分唯一索引配合；将 SQL 放在 Repository 中更
    容易测试并统一项目隔离条件。
    """

    async def list_definitions(
        self,
        project_id: int,
        keyword: str,
        status: AutomationDefinitionStatus | None,
        current: int,
        size: int,
    ) -> tuple[list[AutomationDefinition], int]:
        """分页查询项目内未删除的自动化定义，并加载来源用例和人员信息。"""
        conditions = [
            AutomationDefinition.project_id == project_id,
            AutomationDefinition.deleted_at.is_(None),
        ]
        if keyword:
            conditions.append(
                or_(
                    AutomationDefinition.name.contains(keyword),
                    TestCase.title.contains(keyword),
                    TestCase.case_code.contains(keyword),
                )
            )
        if status is not None:
            conditions.append(AutomationDefinition.status == status.value)

        total = int(
            await self.session.scalar(
                select(func.count(AutomationDefinition.id))
                .join(TestCase, TestCase.id == AutomationDefinition.test_case_id)
                .where(*conditions)
            )
            or 0
        )
        statement = (
            select(AutomationDefinition)
            .join(TestCase, TestCase.id == AutomationDefinition.test_case_id)
            .options(
                selectinload(AutomationDefinition.test_case),
                selectinload(AutomationDefinition.creator),
                selectinload(AutomationDefinition.approver),
            )
            .where(*conditions)
            .order_by(AutomationDefinition.updated_at.desc(), AutomationDefinition.id.desc())
            .offset((current - 1) * size)
            .limit(size)
        )
        return list((await self.session.scalars(statement)).all()), total

    async def get_definition(
        self,
        project_id: int,
        definition_id: int,
        *,
        lock: bool = False,
        include_deleted: bool = False,
    ) -> AutomationDefinition | None:
        """按项目和主键查询定义；审计场景可选择包含已经软删除的记录。"""
        conditions = [
            AutomationDefinition.id == definition_id,
            AutomationDefinition.project_id == project_id,
        ]
        # 普通业务查询不能看见已删除定义；只有不可变审计链查询显式放开。
        if not include_deleted:
            conditions.append(AutomationDefinition.deleted_at.is_(None))
        statement = (
            select(AutomationDefinition)
            .options(
                selectinload(AutomationDefinition.test_case),
                selectinload(AutomationDefinition.creator),
                selectinload(AutomationDefinition.approver),
            )
            .where(*conditions)
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def next_version(self, test_case_id: int) -> int:
        """读取同一来源用例已有最大版本并加一；唯一约束负责最终并发兜底。"""
        latest = await self.session.scalar(
            select(func.max(AutomationDefinition.version)).where(AutomationDefinition.test_case_id == test_case_id)
        )
        return int(latest or 0) + 1

    async def retire_current_approved(
        self,
        test_case_id: int,
        *,
        exclude_definition_id: int,
    ) -> list[AutomationDefinition]:
        """锁定并返回同一用例原来的已审批版本，交给 Service 更新并记录快照。"""
        return list(
            (
                await self.session.scalars(
                    select(AutomationDefinition)
                    .where(
                        AutomationDefinition.test_case_id == test_case_id,
                        AutomationDefinition.id != exclude_definition_id,
                        AutomationDefinition.status == AutomationDefinitionStatus.APPROVED.value,
                        AutomationDefinition.deleted_at.is_(None),
                    )
                    .with_for_update()
                )
            ).all()
        )

    async def list_changes(self, project_id: int, definition_id: int) -> list[AutomationDefinitionChange]:
        """按发生顺序返回一条定义的完整变更链。"""
        return list(
            (
                await self.session.scalars(
                    select(AutomationDefinitionChange)
                    .options(selectinload(AutomationDefinitionChange.changer))
                    .where(
                        AutomationDefinitionChange.project_id == project_id,
                        AutomationDefinitionChange.definition_id == definition_id,
                    )
                    .order_by(AutomationDefinitionChange.id)
                )
            ).all()
        )
