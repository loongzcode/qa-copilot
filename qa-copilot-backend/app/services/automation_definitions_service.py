"""自动化定义转换、编辑、审批和版本管理业务。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.automation.definition_factory import (
    build_automation_definition_from_test_case,
)
from app.core.constants import (
    AutomationDefinitionChangeAction,
    AutomationDefinitionStatus,
    TestCaseStatus,
    TestCaseType,
)
from app.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.mappers.automation_definitions import automation_definition_to_vo
from app.models import AutomationDefinition, AutomationDefinitionChange, User
from app.models.mixins import utc_now
from app.repositories.automation_definitions_repository import (
    AutomationDefinitionsRepository,
)
from app.repositories.test_cases_repository import TestCasesRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.dto.automation_definitions import (
    AutomationDefinitionSpecDTO,
    AutomationDefinitionUpdateDTO,
)
from app.schemas.vo.automation_definitions import AutomationDefinitionChangeVO, AutomationDefinitionVO


class AutomationDefinitionsService:
    """把发布用例转换成安全 JSON，并管理定义的人工审批状态。

    功能：执行项目权限、来源用例资格、受控协议、版本号和状态机校验。
    作用：连接 API、人工测试用例与未来执行器；执行器只能消费 APPROVED 定义。
    为什么用它：Repository 只保证数据库约束，无法表达“已发布 API 用例才能转换”
    等跨实体规则；集中在 Service 可避免不同接口绕过同一安全边界。
    """

    def __init__(
        self,
        repository: AutomationDefinitionsRepository,
        project_repository: TestProjectsRepository,
        test_case_repository: TestCasesRepository,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.test_case_repository = test_case_repository

    async def _require_project(self, project_id: int, current_user: User) -> None:
        """确认当前用户是项目负责人或成员；超级管理员可以访问所有项目。"""
        project = await self.project_repository.get_accessible_project(
            project_id,
            current_user,
        )
        if project is None:
            raise NotFoundException("项目不存在或无权访问")

    @staticmethod
    def _canonical_definition(
        definition: AutomationDefinitionSpecDTO,
    ) -> tuple[dict[str, Any], str]:
        """生成稳定 JSON 和内容摘要，相同内容不受键顺序影响。

        功能：按别名导出协议，再使用固定排序计算 SHA-256（安全哈希算法 256 位）摘要。
        作用：definition 保存给执行器，hash 用于审计、比较和判断来源是否变化。
        为什么用它：直接对 Python 字典转字符串会受键顺序和空格影响；规范化序列化
        可以保证语义相同的定义得到相同摘要。
        """
        payload = definition.model_dump(mode="json", by_alias=True)
        canonical_text = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return payload, hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()

    async def _get_definition(
        self,
        project_id: int,
        definition_id: int,
        *,
        lock: bool = False,
    ) -> AutomationDefinition:
        """读取项目内定义并统一处理不存在或跨项目访问。"""
        definition = await self.repository.get_definition(
            project_id,
            definition_id,
            lock=lock,
        )
        if definition is None:
            raise NotFoundException("自动化定义不存在")
        return definition

    @staticmethod
    def _snapshot(entity: AutomationDefinition) -> dict[str, Any]:
        """提取稳定业务快照；不保存关系对象和数据库内部状态。"""
        return {
            "name": entity.name,
            "version": entity.version,
            "status": entity.status,
            "schema_version": entity.schema_version,
            "source_case_version": entity.source_case_version,
            "definition": entity.definition,
            "definition_hash": entity.definition_hash,
            "approved_by": entity.approved_by,
            "approved_at": entity.approved_at.isoformat() if entity.approved_at else None,
            "retired_at": entity.retired_at.isoformat() if entity.retired_at else None,
            "deleted_at": entity.deleted_at.isoformat() if entity.deleted_at else None,
        }

    def _record_change(
        self,
        entity: AutomationDefinition,
        action: AutomationDefinitionChangeAction,
        current_user: User,
        *,
        before: dict[str, Any] | None,
    ) -> None:
        """把业务变更和审计快照加入同一数据库事务。"""
        self.repository.add(
            AutomationDefinitionChange(
                project_id=entity.project_id,
                test_case_id=entity.test_case_id,
                definition_id=entity.id,
                version=entity.version,
                action=action.value,
                before_snapshot=before,
                after_snapshot=self._snapshot(entity),
                changed_by=current_user.id,
            )
        )

    async def list_definitions(
        self,
        project_id: int,
        current_user: User,
        keyword: str,
        status: AutomationDefinitionStatus | None,
        current: int,
        size: int,
    ) -> tuple[list[AutomationDefinitionVO], int]:
        """分页返回用户有权访问的项目自动化定义。"""
        await self._require_project(project_id, current_user)
        records, total = await self.repository.list_definitions(
            project_id,
            keyword.strip(),
            status,
            current,
            size,
        )
        return [automation_definition_to_vo(record) for record in records], total

    async def get_definition(
        self,
        project_id: int,
        definition_id: int,
        current_user: User,
    ) -> AutomationDefinitionVO:
        """返回一条定义的完整 JSON 和审计字段。"""
        await self._require_project(project_id, current_user)
        return automation_definition_to_vo(await self._get_definition(project_id, definition_id))

    async def create_from_test_case(
        self,
        project_id: int,
        test_case_id: int,
        current_user: User,
    ) -> AutomationDefinitionVO:
        """从一条已发布、可自动化的 API 用例创建新草稿版本。"""
        await self._require_project(project_id, current_user)
        test_case = await self.test_case_repository.get_test_case(
            project_id,
            test_case_id,
            lock=True,
        )
        if test_case is None:
            raise NotFoundException("测试用例不存在")
        if test_case.status != TestCaseStatus.PUBLISHED.value:
            raise BadRequestException("只有已发布测试用例才能生成自动化定义")
        if test_case.case_type != TestCaseType.API.value:
            raise BadRequestException("只有 API 类型测试用例才能生成接口自动化定义")
        if not test_case.automatable:
            raise BadRequestException("该测试用例尚未标记为可自动化")

        spec = build_automation_definition_from_test_case(test_case)
        definition_json, definition_hash = self._canonical_definition(spec)
        entity = AutomationDefinition(
            project_id=project_id,
            test_case_id=test_case.id,
            name=test_case.title,
            version=await self.repository.next_version(test_case.id),
            status=AutomationDefinitionStatus.DRAFT.value,
            schema_version=spec.schema_version,
            source_case_version=test_case.version,
            definition=definition_json,
            definition_hash=definition_hash,
            created_by=current_user.id,
        )
        self.repository.add(entity)
        await self.repository.flush()
        self._record_change(
            entity,
            AutomationDefinitionChangeAction.CREATED,
            current_user,
            before=None,
        )
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("定义版本发生并发冲突，请重试") from exc
        return automation_definition_to_vo(await self._get_definition(project_id, entity.id))

    async def update_definition(
        self,
        project_id: int,
        definition_id: int,
        payload: AutomationDefinitionUpdateDTO,
        current_user: User,
    ) -> AutomationDefinitionVO:
        """编辑草稿名称和完整协议内容；已审批版本不可原地篡改。"""
        await self._require_project(project_id, current_user)
        entity = await self._get_definition(project_id, definition_id, lock=True)
        if entity.status != AutomationDefinitionStatus.DRAFT.value:
            raise ConflictException("只有草稿定义可以编辑")
        before = self._snapshot(entity)
        definition_json, definition_hash = self._canonical_definition(payload.definition)
        entity.name = payload.name
        entity.schema_version = payload.definition.schema_version
        entity.definition = definition_json
        entity.definition_hash = definition_hash
        self._record_change(
            entity,
            AutomationDefinitionChangeAction.UPDATED,
            current_user,
            before=before,
        )
        await self.repository.commit()
        return automation_definition_to_vo(await self._get_definition(project_id, definition_id))

    async def approve_definition(
        self,
        project_id: int,
        definition_id: int,
        current_user: User,
    ) -> AutomationDefinitionVO:
        """审批草稿并在同一事务中退出同用例旧审批版本。"""
        await self._require_project(project_id, current_user)
        entity = await self._get_definition(project_id, definition_id, lock=True)
        if entity.status != AutomationDefinitionStatus.DRAFT.value:
            raise ConflictException("只有草稿定义可以审批")
        before = self._snapshot(entity)
        if (
            entity.test_case.status != TestCaseStatus.PUBLISHED.value
            or entity.test_case.case_type != TestCaseType.API.value
            or not entity.test_case.automatable
            or entity.test_case.version != entity.source_case_version
        ):
            raise ConflictException("来源用例已变更或不再满足自动化条件，请重新生成定义")
        retired_definitions = await self.repository.retire_current_approved(
            entity.test_case_id,
            exclude_definition_id=entity.id,
        )
        for retired_definition in retired_definitions:
            retired_before = self._snapshot(retired_definition)
            retired_definition.status = AutomationDefinitionStatus.RETIRED.value
            retired_definition.retired_at = utc_now()
            self._record_change(
                retired_definition,
                AutomationDefinitionChangeAction.RETIRED,
                current_user,
                before=retired_before,
            )
        entity.status = AutomationDefinitionStatus.APPROVED.value
        entity.approved_by = current_user.id
        entity.approved_at = utc_now()
        entity.retired_at = None
        self._record_change(
            entity,
            AutomationDefinitionChangeAction.APPROVED,
            current_user,
            before=before,
        )
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("同一测试用例已有其他审批操作，请刷新后重试") from exc
        return automation_definition_to_vo(await self._get_definition(project_id, definition_id))

    async def retire_definition(
        self,
        project_id: int,
        definition_id: int,
        current_user: User,
    ) -> AutomationDefinitionVO:
        """让已审批版本退出执行候选，但保留历史审计记录。"""
        await self._require_project(project_id, current_user)
        entity = await self._get_definition(project_id, definition_id, lock=True)
        if entity.status != AutomationDefinitionStatus.APPROVED.value:
            raise ConflictException("只有已审批定义可以退出使用")
        before = self._snapshot(entity)
        entity.status = AutomationDefinitionStatus.RETIRED.value
        entity.retired_at = utc_now()
        self._record_change(
            entity,
            AutomationDefinitionChangeAction.RETIRED,
            current_user,
            before=before,
        )
        await self.repository.commit()
        return automation_definition_to_vo(await self._get_definition(project_id, definition_id))

    async def delete_definition(
        self,
        project_id: int,
        definition_id: int,
        current_user: User,
    ) -> None:
        """软删除草稿或已退出版本；已审批版本必须先退出使用。"""
        await self._require_project(project_id, current_user)
        entity = await self._get_definition(project_id, definition_id, lock=True)
        if entity.status == AutomationDefinitionStatus.APPROVED.value:
            raise ConflictException("已审批定义必须先退出使用再删除")
        before = self._snapshot(entity)
        entity.deleted_at = utc_now()
        self._record_change(
            entity,
            AutomationDefinitionChangeAction.DELETED,
            current_user,
            before=before,
        )
        await self.repository.commit()

    async def list_definition_changes(
        self,
        project_id: int,
        definition_id: int,
        current_user: User,
    ) -> list[AutomationDefinitionChangeVO]:
        """返回定义的不可变审计时间线。"""
        await self._require_project(project_id, current_user)
        # 审计链必须在定义软删除后仍可查看，否则最关键的 DELETED 事件会失去入口。
        definition = await self.repository.get_definition(
            project_id,
            definition_id,
            include_deleted=True,
        )
        if definition is None:
            raise NotFoundException("自动化定义不存在")
        return [
            AutomationDefinitionChangeVO(
                id=item.id,
                definition_id=item.definition_id,
                version=item.version,
                action=AutomationDefinitionChangeAction(item.action),
                before_snapshot=item.before_snapshot,
                after_snapshot=item.after_snapshot,
                changed_by=item.changed_by,
                changed_by_name=item.changer.display_name if item.changer else None,
                created_at=item.created_at,
            )
            for item in await self.repository.list_changes(project_id, definition_id)
        ]
