"""测试工具中心基础管理、预览快照与审批状态机。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.constants import (
    FileTemplateFormat,
    ToolApprovalDecision,
    ToolConnectionType,
    ToolRisk,
    ToolTaskStatus,
    ToolTaskType,
)
from app.core.security import encrypt_secret
from app.exceptions import BadRequestException, ConflictException, ForbiddenException, NotFoundException
from app.models import ExternalConnection, FileTemplate, ToolApproval, ToolExecutionLog, ToolTask, User
from app.repositories.test_projects_repository import TestProjectsRepository
from app.repositories.tool_center_repository import ToolCenterRepository
from app.schemas.api_result import PageResult
from app.schemas.dto.tool_center import (
    ExternalConnectionCreateDTO,
    ExternalConnectionUpdateDTO,
    FileTemplateCreateDTO,
    FileTemplateUpdateDTO,
    ToolApprovalDTO,
    ToolTaskCreateDTO,
    ToolTaskQueryDTO,
)
from app.schemas.vo.tool_center import (
    ExternalConnectionVO,
    FileTemplateVO,
    ToolApprovalVO,
    ToolArtifactVO,
    ToolDefinitionVO,
    ToolLogVO,
    ToolTaskVO,
)

_SECRET_KEYS = {"password", "passwd", "token", "secret", "api_key", "apikey", "access_token", "authorization"}
_TASK_TOOL_CODES = {
    ToolTaskType.FILE_GENERATE: "file.generate",
    ToolTaskType.FILE_VALIDATE: "file.validate",
    ToolTaskType.MYSQL_COMPARE: "mysql.compare",
    ToolTaskType.MYSQL_SYNC: "mysql.sync",
    ToolTaskType.NACOS_COMPARE: "nacos.compare",
    ToolTaskType.NACOS_SYNC: "nacos.sync",
    ToolTaskType.DEFECT_SYNC: "defect.sync",
    ToolTaskType.UI_AUTOMATION: "ui.automation",
}


class ToolCenterService:
    """统一管理工具、连接、模板、预览和人工审批。

    功能：提供工具目录、加密连接、文件模板和统一任务状态机。
    作用：所有文件、MySQL、Nacos 与缺陷同步执行器都通过本服务建立审计边界。
    为什么用它：若每种工具自行处理审批和日志，极易出现绕过；统一底座能确保
    “先预览、再审批、执行前复核哈希”对所有高风险操作都生效。
    """

    def __init__(self, repository: ToolCenterRepository, project_repository: TestProjectsRepository) -> None:
        self.repository = repository
        self.project_repository = project_repository

    async def _require_project(self, project_id: int, current_user: User) -> None:
        if await self.project_repository.get_accessible_project(project_id, current_user) is None:
            raise NotFoundException("项目不存在或无权访问")

    @staticmethod
    def _ensure_no_plain_secrets(value: Any, path: str = "inputData") -> None:
        """递归拒绝任务输入里的明文凭据，强制改用连接 ID。"""
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in _SECRET_KEYS and item not in (None, ""):
                    raise BadRequestException(f"{path}.{key} 不允许保存明文凭据，请选择外部连接")
                ToolCenterService._ensure_no_plain_secrets(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                ToolCenterService._ensure_no_plain_secrets(item, f"{path}[{index}]")

    @staticmethod
    def canonical_hash(value: dict[str, Any]) -> str:
        text_value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(text_value.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_connection_config(
        connection_type: ToolConnectionType,
        config: dict[str, Any],
        credentials: dict[str, str] | None,
    ) -> tuple[dict[str, Any], dict[str, str] | None]:
        """按连接类型只保留执行器认识的字段，并拒绝把凭据混进公开配置。"""
        ToolCenterService._ensure_no_plain_secrets(config, "config")
        credential_keys = {
            ToolConnectionType.MYSQL: {"username", "password"},
            ToolConnectionType.NACOS: {"username", "password", "token"},
            ToolConnectionType.BUSINESS_API: {"token", "api_key"},
            ToolConnectionType.DEFECT_PLATFORM: {"username", "password", "token", "api_key"},
        }[connection_type]
        if credentials is not None:
            unknown_credentials = set(credentials) - credential_keys
            if unknown_credentials:
                raise BadRequestException(
                    f"{connection_type.value} 不支持凭据字段：{', '.join(sorted(unknown_credentials))}"
                )
            credentials = {key: str(value) for key, value in credentials.items() if str(value)}
        if connection_type == ToolConnectionType.MYSQL:
            allowed = {"host", "port", "database", "charset", "timeoutSeconds"}
            required = {"host", "database"}
        elif connection_type in {ToolConnectionType.NACOS, ToolConnectionType.BUSINESS_API}:
            allowed = {"baseUrl", "namespace", "timeoutSeconds", "allowedHosts"}
            required = {"baseUrl"}
        else:
            allowed = {"baseUrl", "createPath", "projectKey", "timeoutSeconds", "allowedHosts"}
            required = {"baseUrl"}
        unknown = set(config) - allowed
        missing = [key for key in required if not str(config.get(key, "")).strip()]
        if unknown:
            raise BadRequestException(f"{connection_type.value} 不支持公开配置字段：{', '.join(sorted(unknown))}")
        if missing:
            raise BadRequestException(f"{connection_type.value} 缺少连接配置：{', '.join(missing)}")
        normalized = {key: value for key, value in config.items() if key in allowed}
        normalized["timeoutSeconds"] = min(max(int(normalized.get("timeoutSeconds", 10)), 1), 30)
        if connection_type == ToolConnectionType.MYSQL:
            normalized["host"] = str(normalized["host"]).strip()
            normalized["database"] = str(normalized["database"]).strip()
            normalized["port"] = min(max(int(normalized.get("port", 3306)), 1), 65535)
            normalized["charset"] = str(normalized.get("charset", "utf8mb4"))
        else:
            normalized["baseUrl"] = str(normalized["baseUrl"]).strip().rstrip("/")
            if connection_type == ToolConnectionType.NACOS:
                normalized["namespace"] = str(normalized.get("namespace", "")).strip()
            if connection_type == ToolConnectionType.DEFECT_PLATFORM:
                normalized["createPath"] = str(normalized.get("createPath", "/api/defects")).strip()
                normalized["projectKey"] = str(normalized.get("projectKey", "")).strip()
        return normalized, credentials

    async def list_tools(self) -> list[ToolDefinitionVO]:
        return [
            ToolDefinitionVO(
                id=item.id,
                code=item.code,
                name=item.name,
                description=item.description,
                risk_level=ToolRisk(item.risk_level),
                required_permission=item.required_permission,
                enabled=item.enabled,
            )
            for item in await self.repository.list_tools()
        ]

    @staticmethod
    def _connection_vo(item: ExternalConnection) -> ExternalConnectionVO:
        return ExternalConnectionVO(
            id=item.id,
            project_id=item.project_id,
            name=item.name,
            connection_type=ToolConnectionType(item.connection_type),
            config=item.config,
            credentials_configured=bool(item.encrypted_credentials),
            enabled=item.enabled,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    async def list_connections(self, project_id: int, current_user: User) -> list[ExternalConnectionVO]:
        await self._require_project(project_id, current_user)
        return [self._connection_vo(item) for item in await self.repository.list_connections(project_id)]

    async def create_connection(
        self, project_id: int, payload: ExternalConnectionCreateDTO, current_user: User
    ) -> ExternalConnectionVO:
        await self._require_project(project_id, current_user)
        config, credentials = self._normalize_connection_config(
            payload.connection_type, payload.config, payload.credentials
        )
        item = ExternalConnection(
            project_id=project_id,
            name=payload.name.strip(),
            connection_type=payload.connection_type.value,
            config=config,
            encrypted_credentials=encrypt_secret(json.dumps(credentials or {}, ensure_ascii=False)),
            enabled=payload.enabled,
            created_by=current_user.id,
        )
        self.repository.add(item)
        await self.repository.commit()
        return self._connection_vo(item)

    async def update_connection(
        self, project_id: int, connection_id: int, payload: ExternalConnectionUpdateDTO, current_user: User
    ) -> ExternalConnectionVO:
        await self._require_project(project_id, current_user)
        item = await self.repository.get_connection(project_id, connection_id)
        if item is None:
            raise NotFoundException("外部连接不存在")
        changes = payload.model_dump(exclude_unset=True)
        credentials = changes.pop("credentials", None)
        config = changes.pop("config", item.config)
        normalized_config, credentials = self._normalize_connection_config(
            ToolConnectionType(item.connection_type), config, credentials
        )
        item.config = normalized_config
        for key, value in changes.items():
            setattr(item, key, value)
        if credentials is not None:
            item.encrypted_credentials = encrypt_secret(json.dumps(credentials, ensure_ascii=False))
        await self.repository.commit()
        return self._connection_vo(item)

    async def delete_connection(self, project_id: int, connection_id: int, current_user: User) -> None:
        await self._require_project(project_id, current_user)
        item = await self.repository.get_connection(project_id, connection_id)
        if item is None:
            raise NotFoundException("外部连接不存在")
        if await self.repository.has_connection_reference(project_id, connection_id):
            raise ConflictException("连接已被工具任务引用，不能删除，可改为停用")
        await self.repository.delete(item)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("连接已被工具任务引用，不能删除，可改为停用") from exc

    @staticmethod
    def _template_vo(item: FileTemplate) -> FileTemplateVO:
        return FileTemplateVO(
            id=item.id,
            project_id=item.project_id,
            name=item.name,
            file_format=FileTemplateFormat(item.file_format),
            encoding=item.encoding,
            delimiter=item.delimiter,
            fields=item.fields,
            header_config=item.header_config,
            trailer_config=item.trailer_config,
            enabled=item.enabled,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    async def list_templates(self, project_id: int, current_user: User) -> list[FileTemplateVO]:
        await self._require_project(project_id, current_user)
        return [self._template_vo(item) for item in await self.repository.list_templates(project_id)]

    async def create_template(
        self, project_id: int, payload: FileTemplateCreateDTO, current_user: User
    ) -> FileTemplateVO:
        await self._require_project(project_id, current_user)
        item = FileTemplate(
            project_id=project_id,
            name=payload.name.strip(),
            file_format=payload.file_format.value,
            encoding=payload.encoding,
            delimiter=payload.delimiter,
            fields=[field.model_dump(mode="json", by_alias=True) for field in payload.fields],
            header_config=payload.header_config,
            trailer_config=payload.trailer_config,
            enabled=payload.enabled,
            created_by=current_user.id,
        )
        self.repository.add(item)
        await self.repository.commit()
        return self._template_vo(item)

    async def update_template(
        self, project_id: int, template_id: int, payload: FileTemplateUpdateDTO, current_user: User
    ) -> FileTemplateVO:
        await self._require_project(project_id, current_user)
        item = await self.repository.get_template(project_id, template_id)
        if item is None:
            raise NotFoundException("文件模板不存在")
        item.name = payload.name.strip()
        item.file_format = payload.file_format.value
        item.encoding = payload.encoding
        item.delimiter = payload.delimiter
        item.fields = [field.model_dump(mode="json", by_alias=True) for field in payload.fields]
        item.header_config = payload.header_config
        item.trailer_config = payload.trailer_config
        item.enabled = payload.enabled
        await self.repository.commit()
        return self._template_vo(item)

    async def create_task(self, project_id: int, payload: ToolTaskCreateDTO, current_user: User) -> ToolTaskVO:
        await self._require_project(project_id, current_user)
        tool = await self.repository.get_tool_by_code(payload.tool_code)
        if tool is None or not tool.enabled:
            raise NotFoundException("工具不存在或已停用")
        if _TASK_TOOL_CODES[payload.task_type] != tool.code:
            raise BadRequestException("任务类型与工具编码不匹配")
        self._ensure_no_plain_secrets(payload.input_data)
        task = ToolTask(
            project_id=project_id,
            tool_id=tool.id,
            task_type=payload.task_type.value,
            title=payload.title.strip(),
            risk_level=tool.risk_level,
            status=ToolTaskStatus.DRAFT.value,
            requested_by=current_user.id,
            input_data=payload.input_data,
        )
        task.tool = tool
        self.repository.add(task)
        # ToolExecutionLog.task_id 是非空外键，必须先 flush 取得数据库生成的任务 ID。
        await self.repository.flush()
        self.repository.add(ToolExecutionLog(task_id=task.id, stage="CREATE", message="工具任务已创建", details={}))
        await self.repository.commit()
        return await self._task_vo(task, detail=True)

    async def save_preview(
        self, project_id: int, task_id: int, preview: dict[str, Any], current_user: User
    ) -> ToolTaskVO:
        await self._require_project(project_id, current_user)
        task = await self.repository.get_task(project_id, task_id, lock=True)
        if task is None:
            raise NotFoundException("工具任务不存在")
        if task.status not in {
            ToolTaskStatus.DRAFT.value,
            ToolTaskStatus.PREVIEWED.value,
            ToolTaskStatus.PENDING_APPROVAL.value,
            ToolTaskStatus.APPROVED.value,
        }:
            raise ConflictException("当前状态不能重新生成预览")
        task.preview_data = preview
        task.preview_hash = self.canonical_hash(preview)
        task.status = (
            ToolTaskStatus.PENDING_APPROVAL.value
            if task.risk_level in {ToolRisk.MEDIUM.value, ToolRisk.HIGH.value}
            else ToolTaskStatus.PREVIEWED.value
        )
        self.repository.add(
            ToolExecutionLog(
                task_id=task.id, stage="PREVIEW", message="已生成只读预览", details={"preview_hash": task.preview_hash}
            )
        )
        await self.repository.commit()
        return await self._task_vo(task, detail=True)

    async def approve_task(
        self, project_id: int, task_id: int, payload: ToolApprovalDTO, current_user: User
    ) -> ToolTaskVO:
        await self._require_project(project_id, current_user)
        task = await self.repository.get_task(project_id, task_id, lock=True)
        if task is None:
            raise NotFoundException("工具任务不存在")
        if task.status != ToolTaskStatus.PENDING_APPROVAL.value or task.preview_hash is None:
            raise ConflictException("任务不在待审批状态或尚未生成预览")
        if task.requested_by == current_user.id and not current_user.is_superuser:
            raise ForbiddenException("高风险任务不能由请求人自行审批")
        self.repository.add(
            ToolApproval(
                task_id=task.id,
                requester_id=task.requested_by,
                approver_id=current_user.id,
                decision=payload.decision.value,
                comment=payload.comment.strip(),
                preview_hash=task.preview_hash,
            )
        )
        task.status = (
            ToolTaskStatus.APPROVED.value
            if payload.decision == ToolApprovalDecision.APPROVED
            else ToolTaskStatus.REJECTED.value
        )
        self.repository.add(
            ToolExecutionLog(
                task_id=task.id,
                stage="APPROVE",
                message="任务已批准" if payload.decision == ToolApprovalDecision.APPROVED else "任务已驳回",
                details={"approver_id": current_user.id},
            )
        )
        await self.repository.commit()
        return await self._task_vo(task, detail=True)

    async def list_tasks(self, project_id: int, query: ToolTaskQueryDTO, current_user: User) -> PageResult[ToolTaskVO]:
        await self._require_project(project_id, current_user)
        records, total = await self.repository.list_tasks(
            project_id,
            status=query.status.value if query.status else None,
            task_type=query.task_type.value if query.task_type else None,
            current=query.current,
            size=query.size,
        )
        return PageResult(
            records=[await self._task_vo(item) for item in records], total=total, current=query.current, size=query.size
        )

    async def get_task(self, project_id: int, task_id: int, current_user: User) -> ToolTaskVO:
        await self._require_project(project_id, current_user)
        task = await self.repository.get_task(project_id, task_id)
        if task is None:
            raise NotFoundException("工具任务不存在")
        return await self._task_vo(task, detail=True)

    async def _task_vo(self, task: ToolTask, *, detail: bool = False) -> ToolTaskVO:
        approvals = await self.repository.list_approvals(task.id) if detail and task.id else []
        logs = await self.repository.list_logs(task.id) if detail and task.id else []
        artifacts = await self.repository.list_artifacts(task.id) if detail and task.id else []
        return ToolTaskVO(
            id=task.id,
            project_id=task.project_id,
            tool_id=task.tool_id,
            tool_code=task.tool.code,
            tool_name=task.tool.name,
            task_type=ToolTaskType(task.task_type),
            title=task.title,
            risk_level=ToolRisk(task.risk_level),
            status=ToolTaskStatus(task.status),
            requested_by=task.requested_by,
            input_data=task.input_data,
            preview_data=task.preview_data,
            preview_hash=task.preview_hash,
            result_data=task.result_data,
            rollback_data=task.rollback_data,
            error_message=task.error_message,
            started_at=task.started_at,
            finished_at=task.finished_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
            approvals=[ToolApprovalVO.model_validate(item, from_attributes=True) for item in approvals],
            logs=[ToolLogVO.model_validate(item, from_attributes=True) for item in logs],
            artifacts=[ToolArtifactVO.model_validate(item, from_attributes=True) for item in artifacts],
        )
