"""原子需求点的业务服务。

需求点虽然属于某条需求，但它拥有独立 CRUD、父子层级、防循环、人工确认和状态回退
规则，因此单独放在一个 Service 中。这样阅读需求主记录代码时不会混入大量需求点逻辑。
"""

from sqlalchemy.exc import IntegrityError

from app.core.constants import RequirementStatus
from app.exceptions import (
    BadRequestException,
    ConflictException,
    InternalServerException,
    NotFoundException,
)
from app.mappers.requirements import requirement_detail_to_vo, requirement_item_to_vo
from app.models import Requirement, RequirementItem, User
from app.models.mixins import utc_now
from app.repositories.requirement_items_repository import RequirementItemsRepository
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.dto.requirements import (
    RequirementItemCreateDTO,
    RequirementItemsConfirmDTO,
    RequirementItemUpdateDTO,
)
from app.schemas.vo.requirements import RequirementDetailVO, RequirementItemVO


class RequirementItemsService:
    """组织需求点写操作所需的数据权限、层级校验和事务。"""

    def __init__(
        self,
        repository: RequirementItemsRepository,
        requirements_repository: RequirementsRepository,
        test_project_repository: TestProjectsRepository,
    ) -> None:
        self.repository = repository
        self.requirements_repository = requirements_repository
        self.test_project_repository = test_project_repository

    async def _get_requirement_for_write(
        self,
        project_id: int,
        requirement_id: int,
        current_user: User,
    ) -> Requirement:
        """统一校验项目权限并锁定需求，供四个写接口复用。

        锁定需求主记录可以防止“一个请求正在确认全部需求点，另一个请求同时新增需求点”
        导致需求状态和真实确认数量不一致。
        """

        project = await self.test_project_repository.get_accessible_project(
            project_id,
            current_user,
        )
        if project is None:
            raise NotFoundException("项目不存在或无权访问")

        requirement = await self.requirements_repository.get_requirement_detail(
            project_id,
            requirement_id,
            lock=True,
        )
        if requirement is None:
            raise NotFoundException("需求不存在")
        if requirement.status == RequirementStatus.EXTRACTING.value:
            raise BadRequestException("需求正在拆解，暂时不能修改需求点")
        if requirement.status == RequirementStatus.ARCHIVED.value:
            raise BadRequestException("已归档需求不能修改需求点")
        return requirement

    async def _validate_parent(
        self,
        requirement_id: int,
        parent_id: int | None,
        *,
        current_item_id: int | None = None,
    ) -> None:
        """校验父需求点属于同一需求，并阻止自己成为自己的祖先。

        更新父级时从新父级一路沿 parent_id 向上查找。如果途中遇到当前需求点，说明
        新关系会形成 A -> B -> A 这样的循环，树形页面和后续遍历都会陷入死循环。
        """

        if parent_id is None:
            return
        current = await self.repository.get_item(requirement_id, parent_id)
        if current is None:
            raise NotFoundException("父需求点不存在或不属于当前需求")

        visited_ids: set[int] = set()
        while current is not None:
            if current.id == current_item_id:
                raise BadRequestException("不能把当前需求点移动到自己的子级下面")
            if current.id in visited_ids:
                raise BadRequestException("需求点层级数据存在循环")
            visited_ids.add(current.id)
            if current.parent_id is None:
                return
            current = await self.repository.get_item(
                requirement_id,
                current.parent_id,
            )
            if current is None:
                raise BadRequestException("需求点父级链不完整")

    @staticmethod
    def _mark_requirement_reviewing(requirement: Requirement) -> None:
        """需求点发生变化后，让需求重新进入待确认状态并更新列表排序时间。"""

        requirement.status = RequirementStatus.REVIEWING.value
        requirement.updated_at = utc_now()

    async def create_requirement_item(
        self,
        project_id: int,
        requirement_id: int,
        payload: RequirementItemCreateDTO,
        current_user: User,
    ) -> RequirementItemVO:
        """人工新增需求点，并把所属需求状态推进到待确认。

        流程：锁定需求 -> 校验父级和编码 -> 创建人工需求点 -> 提交 -> 重新读取。
        """

        requirement = await self._get_requirement_for_write(
            project_id,
            requirement_id,
            current_user,
        )
        await self._validate_parent(requirement_id, payload.parent_id)
        if payload.item_code is not None:
            duplicate = await self.repository.get_item_by_code(
                requirement_id,
                payload.item_code,
            )
            if duplicate is not None:
                raise ConflictException("需求点编码已存在")

        item = RequirementItem(
            requirement_id=requirement_id,
            parent_id=payload.parent_id,
            item_code=payload.item_code,
            title=payload.title,
            description=payload.description,
            item_type=payload.item_type.value,
            priority=payload.priority.value,
            acceptance_criteria=payload.acceptance_criteria,
            source_locator=payload.source_locator,
            ai_generated=False,
            confirmed=False,
            order_no=payload.order_no,
        )
        self.repository.add(item)
        self._mark_requirement_reviewing(requirement)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("需求点编码已存在") from exc

        created_item = await self.repository.get_item(requirement_id, item.id)
        if created_item is None:
            raise InternalServerException("需求点创建后读取失败")
        return requirement_item_to_vo(created_item)

    async def update_requirement_item(
        self,
        project_id: int,
        requirement_id: int,
        item_id: int,
        payload: RequirementItemUpdateDTO,
        current_user: User,
    ) -> RequirementItemVO:
        """人工校正需求点；内容一旦变化，原人工确认自动失效。"""

        requirement = await self._get_requirement_for_write(
            project_id,
            requirement_id,
            current_user,
        )
        item = await self.repository.get_item(requirement_id, item_id, lock=True)
        if item is None:
            raise NotFoundException("需求点不存在")

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return requirement_item_to_vo(item)
        if "parent_id" in changes:
            await self._validate_parent(
                requirement_id,
                changes["parent_id"],
                current_item_id=item_id,
            )
        if "item_code" in changes and changes["item_code"] is not None:
            duplicate = await self.repository.get_item_by_code(
                requirement_id,
                changes["item_code"],
                exclude_item_id=item_id,
            )
            if duplicate is not None:
                raise ConflictException("需求点编码已存在")
        if "item_type" in changes:
            changes["item_type"] = changes["item_type"].value
        if "priority" in changes:
            changes["priority"] = changes["priority"].value

        for field_name, value in changes.items():
            setattr(item, field_name, value)
        # 修改后的内容必须由测试人员重新确认，不能继续沿用旧确认结果。
        item.confirmed = False
        self._mark_requirement_reviewing(requirement)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("需求点编码已存在") from exc

        updated_item = await self.repository.get_item(requirement_id, item_id)
        if updated_item is None:
            raise InternalServerException("需求点更新后读取失败")
        return requirement_item_to_vo(updated_item)

    async def delete_requirement_item(
        self,
        project_id: int,
        requirement_id: int,
        item_id: int,
        current_user: User,
    ) -> None:
        """删除叶子需求点；有子级时拒绝，避免数据库级联删除整棵子树。"""

        requirement = await self._get_requirement_for_write(
            project_id,
            requirement_id,
            current_user,
        )
        item = await self.repository.get_item(requirement_id, item_id, lock=True)
        if item is None:
            raise NotFoundException("需求点不存在")
        if await self.repository.has_children(requirement_id, item_id):
            raise BadRequestException("该需求点仍有子需求点，请先处理子级")

        await self.repository.delete(item)
        await self.repository.flush()
        remaining_count = await self.repository.count_items(requirement_id)
        requirement.status = (
            RequirementStatus.DRAFT.value
            if remaining_count == 0
            else RequirementStatus.REVIEWING.value
        )
        requirement.updated_at = utc_now()
        await self.repository.commit()

    async def confirm_requirement_items(
        self,
        project_id: int,
        requirement_id: int,
        payload: RequirementItemsConfirmDTO,
        current_user: User,
    ) -> RequirementDetailVO:
        """在一个事务中确认多条需求点，并根据剩余未确认数量更新需求状态。"""

        requirement = await self._get_requirement_for_write(
            project_id,
            requirement_id,
            current_user,
        )
        items = await self.repository.get_items_by_ids(
            requirement_id,
            payload.item_ids,
            lock=True,
        )
        if len(items) != len(payload.item_ids):
            raise NotFoundException("部分需求点不存在或不属于当前需求")

        for item in items:
            item.confirmed = True
        await self.repository.flush()
        unconfirmed_count = await self.repository.count_unconfirmed_items(
            requirement_id
        )
        requirement.status = (
            RequirementStatus.CONFIRMED.value
            if unconfirmed_count == 0
            else RequirementStatus.REVIEWING.value
        )
        requirement.updated_at = utc_now()
        await self.repository.commit()

        updated_requirement = await self.requirements_repository.get_requirement_detail(
            project_id,
            requirement_id,
        )
        if updated_requirement is None:
            raise InternalServerException("需求点确认后读取需求失败")
        return requirement_detail_to_vo(updated_requirement)
