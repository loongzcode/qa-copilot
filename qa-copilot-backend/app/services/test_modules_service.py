from sqlalchemy.exc import IntegrityError

from app.core.constants import ProjectStatus
from app.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models import TestModule, User
from app.repositories.test_modules_repository import TestModulesRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.dto.test_modules import TestModuleCreateDTO, TestModuleUpdateDTO
from app.schemas.vo.test_modules import TestModuleVO


class TestModulesService:
    def __init__(self, repository: TestModulesRepository, project_repository: TestProjectsRepository) -> None:
        self.repository = repository
        self.project_repository = project_repository

    @staticmethod
    def _module_read(module: TestModule) -> TestModuleVO:
        return TestModuleVO(
            id=module.id,
            project_id=module.project_id,
            parent_id=module.parent_id,
            name=module.name,
            code=module.code,
            description=module.description,
            order_no=module.order_no,
            asset_count=module.asset_count or 0,
            created_at=module.created_at,
            updated_at=module.updated_at,
        )

    @classmethod
    def _build_module_tree(cls, modules: list[TestModule]) -> list[TestModuleVO]:
        # 先把每个实体类转换成VO，并通过模块ID建立索引
        node_map: dict[int, TestModuleVO] = {module.id: cls._module_read(module) for module in modules}
        roots: list[TestModuleVO] = []
        for module in modules:
            current_node = node_map[module.id]
            if module.parent_id is None:
                # 没有 parent_id，说明它是一级模块。
                roots.append(current_node)
                continue
            parent_node = node_map.get(module.parent_id)
            if parent_node is None:
                # 数据异常或父模块不在本次结果中时，避免节点直接丢失。
                roots.append(current_node)
                continue
            parent_node.children.append(current_node)
        return roots

    """
    遍历每个模块：

    先过滤它的子模块

    如果当前模块匹配：
        保留

    否则如果它的子模块有匹配：
        也保留，因为要展示父级路径

    否则：
        丢弃
    """

    @classmethod
    def _filter_module_tree(
        cls,
        nodes: list[TestModuleVO],
        keyword: str,
    ) -> list[TestModuleVO]:
        """根据关键词过滤模块树，同时保留命中节点的父级路径。"""

        # 去掉关键词两侧空格，并转换为小写，实现不区分大小写搜索。
        search_text = keyword.strip().lower()

        # 没有输入关键词时不需要过滤，直接返回原来的模块树。
        if not search_text:
            return nodes

        # 保存本层过滤后需要返回的模块节点。
        result: list[TestModuleVO] = []

        # 依次检查当前层的每一个模块节点。
        for node in nodes:
            # 递归过滤当前模块的子模块。
            #
            # 例如当前节点是“支付模块”，它的子模块中包含“支付退款”，
            # 搜索“退款”后 filtered_children 中会保留“支付退款”。
            filtered_children = cls._filter_module_tree(
                node.children,
                search_text,
            )

            # 把模块名称、编码和说明组合起来进行搜索。
            # 转换为小写后，可以支持 PAY_ORDER、pay_order 等不同输入形式。
            content = f"{node.name} {node.code} {node.description}".lower()

            # 判断当前模块自身是否匹配关键词。
            current_matched = search_text in content

            # 满足以下任意条件就保留当前节点：
            # 1. 当前模块自身匹配；
            # 2. 当前模块的子模块中存在匹配项。
            #
            # 第二个条件可以保留父级路径。
            if current_matched or filtered_children:
                # model_copy() 会复制一个新的 VO，避免直接修改原来的模块树。
                # children 替换为过滤后的子模块列表。
                filtered_node = node.model_copy(
                    update={
                        "children": filtered_children,
                    }
                )
                result.append(filtered_node)

        # 返回当前层过滤后的节点。
        return result

    async def list_modules(
        self,
        project_id: int,
        current_user: User,
        keyword: str,
    ) -> list[TestModuleVO]:
        """查询当前用户有权访问的项目模块树。"""

        # 先查询当前用户有权访问的项目。
        # 普通用户只能查询自己的项目，超级管理员可以查询所有项目。
        project = await self.project_repository.get_accessible_project(
            project_id,
            current_user,
        )

        # 返回 None 可能有两种情况：
        # 1. 项目确实不存在；
        # 2. 项目存在，但当前用户没有访问权限。
        #
        # 对外统一返回“项目不存在或无权访问”，避免泄露其他人的项目信息。
        if project is None:
            raise NotFoundException("项目不存在或无权访问")

        # Repository 从数据库查询这个项目的全部模块。
        # 这里拿到的是扁平的 TestModule 实体列表。
        modules = await self.repository.list_modules(project_id)

        # 根据 parent_id 把扁平列表组装成树。
        module_tree = self._build_module_tree(modules)

        # 根据关键词过滤树。
        # 关键词为空时，_filter_module_tree() 会直接返回完整模块树。
        return self._filter_module_tree(
            module_tree,
            keyword,
        )

    async def create_module(self, project_id: int, payload: TestModuleCreateDTO, current_user: User) -> TestModuleVO:
        # 查询当前用户有权访问的项目
        project = await self.project_repository.get_accessible_project(project_id, current_user)
        # 项目不存在或无权访问时抛出异常
        if project is None:
            raise NotFoundException("项目不存在或无权访问")
        # 已归档项目不能创建模块
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不能管理模块")
        # 如果传了 parent_id，查询当前项目中的父模块
        if payload.parent_id is not None:
            parent = await self.repository.get_module(project_id, payload.parent_id)
            # 父模块不存在时抛出异常
            if parent is None:
                raise BadRequestException("父模块不存在")
        # 根据 DTO 创建 TestModule 实体
        module = TestModule(
            project_id=project_id,
            parent_id=payload.parent_id,
            name=payload.name,
            code=payload.code,
            description=payload.description,
            order_no=payload.order_no,
        )
        # 将实体添加到 Session
        self.repository.add(module)
        # 提交事务
        # 捕获数据库唯一约束异常并回滚
        try:
            await self.repository.commit()
        except IntegrityError as e:
            await self.repository.rollback()
            raise ConflictException("模块已存在") from e
        # 将创建完成的实体转换成 VO 返回
        return self._module_read(module)

    async def update_module(
        self,
        project_id: int,
        module_id: int,
        payload: TestModuleUpdateDTO,
        current_user: User,
    ) -> TestModuleVO:
        # 查询当前用户有权访问的项目
        project = await self.project_repository.get_accessible_project(project_id, current_user)
        # 项目不存在或无权访问时抛出异常
        if project is None:
            raise NotFoundException("项目不存在或无权访问")
        # 已归档项目不能编辑模块
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不能编辑模块")
        # 根据 project_id 和 module_id 查询模块
        module = await self.repository.get_module(project_id, module_id)
        # 模块不存在时抛出异常
        if module is None:
            raise NotFoundException("模块不存在")
        # 提取前端实际传入的修改字段
        changes = payload.model_dump(exclude_unset=True)
        # 如果前端传了 parent_id
        if "parent_id" in changes:
            # 取出新的父模块 ID
            new_parent_id = changes["parent_id"]
            # 不能把当前模块设置为自己的父模块
            if new_parent_id == module.id:
                raise BadRequestException("模块不能成为自己的父模块")
            # 新父模块不为空时
            if new_parent_id is not None:
                # 同时传 project_id，确保查询到的是当前项目的模块。
                parent = await self.repository.get_module(
                    project_id,
                    new_parent_id,
                )
                if parent is None:
                    raise BadRequestException("父模块不存在")
                # 判断新父模块是否位于当前模块的子树中。
                creates_cycle = await self.repository.is_descendant(
                    project_id=project_id,
                    ancestor_id=module.id,
                    descendant_id=new_parent_id,
                )

                # 如果把当前模块移动到自己的子模块下面，就会形成循环。
                if creates_cycle:
                    raise BadRequestException("不能将模块移动到自己的子模块下面")

        # 循环修改实体字段
        for key, value in changes.items():
            setattr(module, key, value)
        # 提交事务，编码重复时回滚
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("当前项目中已存在相同模块标识") from exc
        # 转换成 VO 返回
        return self._module_read(module)

    async def delete_module(
        self,
        project_id: int,
        module_id: int,
        current_user: User,
    ) -> None:
        # 查询当前用户有权访问的项目
        project = await self.project_repository.get_accessible_project(project_id, current_user)
        # 项目不存在或无权访问时抛出异常
        if project is None:
            raise NotFoundException("项目不存在或无权访问")
        # 已归档项目不能删除模块
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不能删除模块")
        # 根据 project_id 和 module_id 查询模块
        module = await self.repository.get_module(project_id, module_id)
        # 模块不存在时抛出异常
        if module is None:
            raise NotFoundException("模块不存在")
        # 调用 Repository 删除模块实体
        await self.repository.delete(module)
        # 提交事务
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            # 删除失败时回滚并抛出冲突异常
            raise ConflictException("删除失败") from exc
