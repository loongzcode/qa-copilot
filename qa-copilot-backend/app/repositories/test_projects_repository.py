from sqlalchemy import column, exists, func, or_, select, table
from sqlalchemy.orm import selectinload, with_expression

from app.core.constants import ProjectStatus
from app.models import TestProjectMember, User
from app.models.test_projects import TestProjects
from app.repositories.base_repository import BaseRepository

# `test_project_members` 和 `test_modules` 暂时没有对应的 ORM 实体类。
# 这里用 table() 创建“轻量级表对象”，只声明统计时需要的 project_id 字段。
# 它不会创建或修改数据库表，只是让 SQLAlchemy 知道 SQL 中使用的表名和列名。
project_members_table = table(
    "test_project_members",
    column("project_id"),
)
project_modules_table = table(
    "test_modules",
    column("project_id"),
)


class TestProjectsRepository(BaseRepository):

    @staticmethod
    def _user_can_access_project(user_id: int):
        member_exists = exists().where(
            TestProjectMember.project_id == TestProjects.id,
            TestProjectMember.user_id == user_id,
        )

        return or_(
            TestProjects.owner_id == user_id,
            member_exists,
        )

    async def list_projects(
        self,
        current_user: User,
        current: int,
        size: int,
        keyword: str,
        status: ProjectStatus | None,
    ):
        """分页查询项目，并补充负责人、成员数和模块数。

        查询过程可以分成四步：
        1. 根据 keyword 组合搜索条件；
        2. 准备成员数、模块数两个统计子查询；
        3. 查询符合条件的项目总数；
        4. 根据 current 和 size 查询当前页数据。

        返回值是 ``(项目列表, 总记录数)``。
        """

        # 把查询条件统一放进列表，最后通过 where(*conditions) 一次应用。
        # 如果 keyword 为空，conditions 就是空列表，代表不添加搜索条件。
        conditions = [TestProjects.deleted_at.is_(None)]
        # 超级管理员不添加项目范围条件，因此可以看到所有项目。
        # 普通用户必须是项目负责人或项目成员，才能看到对应项目。
        if not current_user.is_superuser:
            conditions.append(
                self._user_can_access_project(current_user.id)
            )
        if status is not None:
            conditions.append(TestProjects.status == status.value)
        if keyword:
            # or_(条件1, 条件2, ...) 表示任意一个条件成立即可。
            # contains(keyword) 会生成类似 SQL：column LIKE '%keyword%'。
            # User 字段能够出现在这里，是因为下面的主查询关联了 users 表。
            conditions.append(
                or_(
                    TestProjects.name.contains(keyword),
                    TestProjects.code.contains(keyword),
                    User.display_name.contains(keyword),
                    User.username.contains(keyword),
                )
            )

        # 统计当前项目的成员数量。
        # 对于外层查询中的每一个 TestProjects.id，这段表达式都会生成类似 SQL：
        # SELECT count(*)
        # FROM test_project_members
        # WHERE test_project_members.project_id = test_projects.id
        member_count_expression = (
            # func.count() 表示调用数据库的 COUNT(*) 函数。
            select(func.count())
            # select_from() 明确告诉 SQLAlchemy 从哪张表进行统计。
            .select_from(project_members_table)
            # `.c` 是轻量级表对象访问列的方式，`.c.project_id` 就是 project_id 列。
            .where(project_members_table.c.project_id == TestProjects.id)
            # correlate() 表示子查询中的 TestProjects.id 来自外层的项目查询，
            # 不要在子查询中再次把 test_projects 作为独立表查询。
            .correlate(TestProjects)
            # scalar_subquery() 把 SELECT 子查询转换成一个“单值表达式”，
            # 这样它可以像普通字段一样放进外层 SELECT 中。
            .scalar_subquery()
        )

        # 模块数量的统计方式与成员数量相同，只是换成 test_modules 表。
        module_count_expression = (
            select(func.count())
            .select_from(project_modules_table)
            .where(project_modules_table.c.project_id == TestProjects.id)
            .correlate(TestProjects)
            .scalar_subquery()
        )

        # 主查询：select(TestProjects) 表示查询项目实体。
        base_query = (
            select(TestProjects)
            # LEFT OUTER JOIN users ON test_projects.owner_id = users.id。
            # 使用 outerjoin 而不是 join，是为了让 owner_id 为空的项目也能被查出来。
            .outerjoin(
                User,
                TestProjects.owner_id == User.id,
            ).options(
                # selectinload 会再执行一条批量用户查询，把负责人对象放到 project.owner。
                # 它不会为每个项目分别查询一次，因此可以避免 N+1 查询问题。
                selectinload(TestProjects.owner),
                # member_count 和 module_count 在实体中是 query_expression，
                # 不是数据库真实字段。with_expression() 用上面的统计结果填充它们。
                with_expression(TestProjects.member_count, member_count_expression),
                with_expression(TestProjects.module_count, module_count_expression),
            )
            # `*conditions` 会把列表展开。
            # 例如 [condition1, condition2] 会变成 where(condition1, condition2)，
            # 多个 where 参数之间是 AND 关系。
            .where(*conditions)
        )

        # 总数查询只统计符合搜索条件的项目数量，不加载完整项目内容。
        # 这个 total 会交给前端的分页组件，用来计算总页数。
        total_query = (
            select(func.count(TestProjects.id))
            .select_from(TestProjects)
            # 搜索负责人姓名或用户名需要关联 users 表，因此总数查询也要做相同关联。
            .outerjoin(
                User,
                TestProjects.owner_id == User.id,
            )
            .where(*conditions)
        )

        # session.scalar() 只取查询结果第一行、第一列的值。
        # COUNT 在正常情况下会返回数字；`or 0` 是额外的空值保护。
        total = await self.session.scalar(total_query) or 0

        # session.scalars() 与 scalar() 不同：
        # - scalar() 取一个值，适合查询总数或单条记录；
        # - scalars() 获取多行结果中的第一列，这里第一列就是 TestProjects 实体。
        records = list(
            (
                await self.session.scalars(
                    base_query
                    # id.desc() 表示按项目 ID 倒序，新创建的项目排在前面。
                    .order_by(TestProjects.id.desc())
                    # offset() 跳过前面页的数据。
                    # 第 1 页跳过 0 条，第 2 页跳过 size 条，以此类推。
                    .offset((current - 1) * size)
                    # limit() 限制本页最多返回 size 条数据。
                    .limit(size)
                )
                # all() 读取本页的全部结果，再转成普通 list 返回。
            ).all()
        )

        # Repository 返回原始实体和总数，实体转 VO 的工作由 Service 完成。
        return records, total

    async def get_accessible_project(
        self, project_id: int, current_user: User
    ) -> TestProjects | None:
        """查询当前用户有权操作的项目。"""
        conditions = [
            TestProjects.id == project_id,
            TestProjects.deleted_at.is_(None),
        ]
        if not current_user.is_superuser:
            conditions.append(
                self._user_can_access_project(current_user.id)
            )

        project = await self.session.scalar(
            select(TestProjects)
            .options(selectinload(TestProjects.owner))
            .where(*conditions)
        )
        if project is None:
            return None
        member_count = await self.session.scalar(
            select(func.count())
            .select_from(project_members_table)
            .where(project_members_table.c.project_id == project.id)
        )
        module_count = await self.session.scalar(
            select(func.count())
            .select_from(project_modules_table)
            .where(project_modules_table.c.project_id == project.id)
        )

        project.member_count = member_count or 0
        project.module_count = module_count or 0
        return project
