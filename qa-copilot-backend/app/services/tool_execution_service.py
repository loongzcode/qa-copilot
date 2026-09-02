"""工具任务服务器端预览、执行、产物保存和回滚编排。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.prompts import ChatPromptTemplate

from app.automation.controlled_ui_runner import UIAutomationSpecDTO, execute_playwright_ui
from app.core.constants import AIModelTaskType, ToolRisk, ToolTaskStatus, ToolTaskType
from app.core.security import decrypt_secret, encrypt_secret
from app.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models import ExternalConnection, ToolArtifact, ToolExecutionLog, ToolTask, User
from app.models.mixins import utc_now
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.repositories.tool_center_repository import ToolCenterRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.schemas.dto.tool_center import AIFileRecordsGenerateDTO
from app.schemas.vo.tool_center import AIFileRecordsPreviewVO, ToolTaskVO
from app.services.tool_center_service import ToolCenterService
from app.storage.base import DocumentStorage
from app.tools.defect_tools import DefectPlatformClient, build_defect_payload
from app.tools.file_tools import generate_file, parse_file, validate_records
from app.tools.mysql_tools import (
    capture_mysql_snapshot,
    compare_mysql_snapshots,
    execute_mysql_ddl,
    execute_mysql_rollback,
)
from app.tools.nacos_tools import NacosClient, compare_nacos_content, content_hash
from app.utils.ai_client_util import generate_text_with_langchain


class ToolExecutionService:
    """根据工具类型生成可信预览，并在状态机保护下执行或回滚。

    功能：从加密连接读取凭据、调用固定工具实现、复核预览哈希并保存日志产物。
    作用：API 和未来 Agent 都只能调用这里；Agent 不能直接获得 execute 能力。
    为什么用它：预览必须由服务器计算，若接受前端传入的预览，高风险审批可被伪造；
    执行前再算一次还能发现外部 Schema/配置在审批后已经变化。
    """

    def __init__(
        self,
        repository: ToolCenterRepository,
        project_repository: TestProjectsRepository,
        storage: DocumentStorage,
        ai_model_repository: AIModelRepository,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.storage = storage
        self.ai_model_repository = ai_model_repository
        self.center_service = ToolCenterService(repository, project_repository)

    async def generate_ai_file_records(
        self,
        project_id: int,
        template_id: int,
        payload: AIFileRecordsGenerateDTO,
        current_user: User,
    ) -> AIFileRecordsPreviewVO:
        """读取模板后用 AI 生成合成测试记录，并用固定规则再次校验。

        功能：把用户提供的数量、场景和约束转换为模板字段对应的 JSON 记录。
        作用：位于自然语言输入和 file.generate 固定执行器之间，避免用户手写所有字段。
        为什么用它：模型只负责构造候选数据；最终是否合格仍由 validate_records 决定，
        这样日期、必填和精度等规则不会因为模型“认为正确”而被绕过。
        """
        await self.center_service._require_project(project_id, current_user)
        template = await self.repository.get_template(project_id, template_id)
        if template is None or not template.enabled:
            raise NotFoundException("文件模板不存在或已停用")
        model = await self.ai_model_repository.get_default_model()
        if model is None or not model.enabled or not model.provider.enabled:
            raise BadRequestException("未配置可用的默认 AI 模型")
        supported_tasks = set(model.task_types or [])
        if not supported_tasks.intersection(
            {AIModelTaskType.TEST_CASE_GENERATION.value, AIModelTaskType.SUPERVISOR_PLANNING.value}
        ):
            raise BadRequestException("默认模型需要支持测试用例生成或 Supervisor 规划")
        generation_task_type = (
            AIModelTaskType.TEST_CASE_GENERATION.value
            if AIModelTaskType.TEST_CASE_GENERATION.value in supported_tasks
            else AIModelTaskType.SUPERVISOR_PLANNING.value
        )

        field_rules = [
            {
                "name": field.get("name"),
                "source_field": field.get("sourceField"),
                "data_type": field.get("dataType"),
                "required": field.get("required", False),
                "length": field.get("length"),
                "precision": field.get("precision"),
                "format": field.get("format"),
            }
            for field in template.fields
        ]
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是测试数据生成器。只生成合成测试数据，不得输出真实个人信息。"
                    # ChatPromptTemplate 会把单花括号识别为运行变量；双花括号表示这里是 JSON 示例文本。
                    "必须严格返回 JSON 对象 {{\"records\": [...]}}，不要输出 Markdown 或解释。"
                    "每条记录只能使用字段规则中的 source_field 作为键。",
                ),
                (
                    "human",
                    "模板字段规则：\n{field_rules}\n\n生成数量：{count}\n"
                    "场景分布：{scenarios}\n补充约束：{constraints}\n"
                    "请保证日期、数据类型、必填和小数精度符合字段规则。",
                ),
            ]
        )
        last_errors: list[dict[str, Any]] = []
        generation = None
        for _attempt in range(2):
            generation = await generate_text_with_langchain(
                repository=self.ai_model_repository,
                provider=model.provider,
                model=model,
                chat_prompt=prompt,
                input_variables={
                    "field_rules": json.dumps(field_rules, ensure_ascii=False),
                    "count": payload.count,
                    "scenarios": payload.scenarios,
                    "constraints": payload.constraints
                    + (
                        "\n上次校验错误，请修复："
                        + json.dumps(last_errors[:20], ensure_ascii=False)
                        if last_errors
                        else ""
                    ),
                },
                task_type=generation_task_type,
                max_output_tokens=8192,
                reasoning_effort="minimal",
                usage_context=AIUsageContextDTO(
                    user_id=current_user.id,
                    project_id=project_id,
                    task_id=f"file-template:{template_id}:ai-records",
                ),
            )
            raw = generation.content.strip()
            fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
            if fenced:
                raw = fenced.group(1)
            try:
                parsed = json.loads(raw)
                records = parsed.get("records") if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                records = None
            if not isinstance(records, list) or len(records) != payload.count or any(
                not isinstance(item, dict) for item in records
            ):
                last_errors = [{"message": f"模型必须返回恰好 {payload.count} 条对象记录"}]
                continue
            _, last_errors = validate_records(records, template.fields)
            if not last_errors:
                return AIFileRecordsPreviewVO(
                    records=records,
                    validation_errors=[],
                    model_id=model.id,
                    input_tokens=generation.input_tokens,
                    output_tokens=generation.output_tokens,
                )
        raise BadRequestException(
            "AI 两次生成后仍未通过模板校验：" + "；".join(str(item.get("message", item)) for item in last_errors[:5])
        )

    async def _require_task(self, project_id: int, task_id: int, current_user: User, *, lock: bool = False) -> ToolTask:
        await self.center_service._require_project(project_id, current_user)
        task = await self.repository.get_task(project_id, task_id, lock=lock)
        if task is None:
            raise NotFoundException("工具任务不存在")
        return task

    async def _connection(
        self, project_id: int, connection_id: int, expected_type: str
    ) -> tuple[ExternalConnection, dict[str, str]]:
        connection = await self.repository.get_connection(project_id, connection_id)
        if connection is None or not connection.enabled:
            raise NotFoundException("外部连接不存在或已停用")
        if connection.connection_type != expected_type:
            raise BadRequestException(f"必须选择 {expected_type} 类型连接")
        try:
            credentials = json.loads(decrypt_secret(connection.encrypted_credentials) or "{}")
        except (ValueError, TypeError) as exc:
            raise BadRequestException("外部连接凭据无法解密或格式损坏") from exc
        return connection, credentials

    async def _build_preview(self, task: ToolTask) -> dict[str, Any]:
        data = task.input_data
        task_type = ToolTaskType(task.task_type)
        if task_type in {ToolTaskType.FILE_GENERATE, ToolTaskType.FILE_VALIDATE}:
            template_id = int(data.get("template_id", 0))
            template = await self.repository.get_template(task.project_id, template_id)
            if template is None or not template.enabled:
                raise NotFoundException("文件模板不存在或已停用")
            if task_type == ToolTaskType.FILE_GENERATE:
                records = data.get("records", [])
                if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
                    raise BadRequestException("records 必须是对象数组")
                _, errors = validate_records(records, template.fields)
                return {
                    "summary": f"将按 {template.name} 生成 {len(records)} 条记录",
                    "template_id": template.id,
                    "format": template.file_format,
                    "record_count": len(records),
                    "validation_errors": errors,
                    "warnings": [],
                    "requires_approval": False,
                }
            artifact_id = int(data.get("input_artifact_id", 0))
            artifacts = await self.repository.list_artifacts(task.id)
            artifact = next(
                (item for item in artifacts if item.id == artifact_id and item.artifact_type == "INPUT"), None
            )
            if artifact is None:
                raise BadRequestException("请先上传需要校验的文件")
            return {
                "summary": f"将使用模板 {template.name} 校验文件 {artifact.name}",
                "template_id": template.id,
                "input_artifact_id": artifact.id,
                "format": template.file_format,
                "warnings": [],
                "requires_approval": False,
            }
        if task_type in {ToolTaskType.MYSQL_COMPARE, ToolTaskType.MYSQL_SYNC}:
            source, source_credentials = await self._connection(
                task.project_id, int(data.get("source_connection_id", 0)), "MYSQL"
            )
            target, target_credentials = await self._connection(
                task.project_id, int(data.get("target_connection_id", 0)), "MYSQL"
            )
            source_snapshot, target_snapshot = await asyncio.gather(
                capture_mysql_snapshot(source.config, source_credentials),
                capture_mysql_snapshot(target.config, target_credentials),
            )
            comparison = compare_mysql_snapshots(source_snapshot, target_snapshot)
            comparison.update(
                {
                    "summary": f"比较 {source.name} → {target.name}",
                    "source_connection_id": source.id,
                    "target_connection_id": target.id,
                    "source_snapshot": source_snapshot,
                    "target_snapshot": target_snapshot,
                }
            )
            return comparison
        if task_type in {ToolTaskType.NACOS_COMPARE, ToolTaskType.NACOS_SYNC}:
            source, source_credentials = await self._connection(
                task.project_id, int(data.get("source_connection_id", 0)), "NACOS"
            )
            target, target_credentials = await self._connection(
                task.project_id, int(data.get("target_connection_id", 0)), "NACOS"
            )
            data_id = str(data.get("data_id", "")).strip()
            group = str(data.get("group", "DEFAULT_GROUP")).strip()
            config_type = str(data.get("config_type", "yaml")).strip().lower()
            if not data_id:
                raise BadRequestException("Nacos Data ID 不能为空")
            source_content, target_content = await asyncio.gather(
                NacosClient(source.config, source_credentials).get_config(data_id, group),
                NacosClient(target.config, target_credentials).get_config(data_id, group),
            )
            comparison = compare_nacos_content(source_content, target_content, config_type)
            comparison.update(
                {
                    "summary": f"比较 {source.name} → {target.name} / {group} / {data_id}",
                    "source_connection_id": source.id,
                    "target_connection_id": target.id,
                    "data_id": data_id,
                    "group": group,
                    "config_type": config_type,
                }
            )
            return comparison
        if task_type == ToolTaskType.DEFECT_SYNC:
            connection, _ = await self._connection(
                task.project_id,
                int(data.get("connection_id", 0)),
                "DEFECT_PLATFORM",
            )
            payload = build_defect_payload(data, str(connection.config.get("projectKey", "")))
            return {
                "summary": f"向 {connection.name} 创建缺陷：{payload['title']}",
                "connection_id": connection.id,
                "payload": payload,
                "warnings": [],
                "requires_approval": True,
            }
        if task_type == ToolTaskType.UI_AUTOMATION:
            connection, _ = await self._connection(
                task.project_id,
                int(data.get("connection_id", 0)),
                "BUSINESS_API",
            )
            spec = UIAutomationSpecDTO.model_validate(
                {"steps": data.get("steps", []), "variables": data.get("variables", {})}
            )
            return {
                "summary": f"将在 {connection.name} 顺序执行 {len(spec.steps)} 个受控浏览器步骤",
                "connection_id": connection.id,
                "steps": spec.model_dump(mode="json", by_alias=True)["steps"],
                "warnings": ["候选定位器命中后只生成待人工确认的自愈建议，不会自动修改正式定义"],
                "requires_approval": True,
            }
        raise BadRequestException("该工具类型尚未注册执行器")

    async def preview(self, project_id: int, task_id: int, current_user: User) -> ToolTaskVO:
        task = await self._require_task(project_id, task_id, current_user)
        preview = await self._build_preview(task)
        return await self.center_service.save_preview(project_id, task_id, preview, current_user)

    async def attach_input_file(
        self, project_id: int, task_id: int, filename: str, content_type: str, content: bytes, current_user: User
    ) -> ToolTaskVO:
        task = await self._require_task(project_id, task_id, current_user, lock=True)
        if task.task_type != ToolTaskType.FILE_VALIDATE.value or task.status not in {
            ToolTaskStatus.DRAFT.value,
            ToolTaskStatus.PREVIEWED.value,
        }:
            raise ConflictException("只有草稿或已预览的文件校验任务可以上传输入文件")
        if not content or len(content) > 50 * 1024 * 1024:
            raise BadRequestException("校验文件必须大于 0 且不超过 50MB")
        suffix = Path(filename).suffix.lower()[:20]
        object_key = f"tool-artifacts/{project_id}/{task.id}/input-{uuid4().hex}{suffix}"
        descriptor, path = tempfile.mkstemp(prefix="qa-tool-input-", suffix=suffix)
        os.close(descriptor)
        temp_path = Path(path)
        await asyncio.to_thread(temp_path.write_bytes, content)
        await self.storage.save_file(temp_path, object_key)
        artifact = ToolArtifact(
            task_id=task.id,
            artifact_type="INPUT",
            name=Path(filename).name,
            object_key=object_key,
            content_type=content_type or "application/octet-stream",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        self.repository.add(artifact)
        await self.repository.flush()
        task.input_data = {**task.input_data, "input_artifact_id": artifact.id}
        task.preview_data = None
        task.preview_hash = None
        task.status = ToolTaskStatus.DRAFT.value
        await self.repository.commit()
        return await self.center_service._task_vo(task, detail=True)

    async def _read_artifact(self, artifact: ToolArtifact) -> bytes:
        descriptor, path = tempfile.mkstemp(prefix="qa-tool-read-")
        os.close(descriptor)
        temp_path = Path(path)
        try:
            await self.storage.download_file(artifact.object_key, temp_path)
            return await asyncio.to_thread(temp_path.read_bytes)
        finally:
            temp_path.unlink(missing_ok=True)

    async def _save_artifact(
        self, task: ToolTask, *, name: str, content_type: str, content: bytes, artifact_type: str
    ) -> ToolArtifact:
        suffix = Path(name).suffix
        object_key = f"tool-artifacts/{task.project_id}/{task.id}/{uuid4().hex}{suffix}"
        descriptor, path = tempfile.mkstemp(prefix="qa-tool-output-", suffix=suffix)
        os.close(descriptor)
        temp_path = Path(path)
        await asyncio.to_thread(temp_path.write_bytes, content)
        await self.storage.save_file(temp_path, object_key)
        artifact = ToolArtifact(
            task_id=task.id,
            artifact_type=artifact_type,
            name=name,
            object_key=object_key,
            content_type=content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        self.repository.add(artifact)
        await self.repository.flush()
        return artifact

    async def execute(self, project_id: int, task_id: int, current_user: User) -> ToolTaskVO:
        task = await self._require_task(project_id, task_id, current_user, lock=True)
        allowed_status = (
            ToolTaskStatus.APPROVED.value
            if task.risk_level in {ToolRisk.MEDIUM.value, ToolRisk.HIGH.value}
            else ToolTaskStatus.PREVIEWED.value
        )
        if task.status != allowed_status or task.preview_hash is None:
            raise ConflictException("任务尚未完成有效预览或审批")
        latest_preview = await self._build_preview(task)
        latest_hash = self.center_service.canonical_hash(latest_preview)
        if latest_hash != task.preview_hash:
            task.preview_data = latest_preview
            task.preview_hash = latest_hash
            task.status = (
                ToolTaskStatus.PENDING_APPROVAL.value
                if task.risk_level in {ToolRisk.MEDIUM.value, ToolRisk.HIGH.value}
                else ToolTaskStatus.PREVIEWED.value
            )
            self.repository.add(
                ToolExecutionLog(
                    task_id=task.id,
                    stage="SNAPSHOT_RECHECK",
                    level="WARNING",
                    message="外部快照已变化，原审批失效",
                    details={"preview_hash": latest_hash},
                )
            )
            await self.repository.commit()
            raise ConflictException("预览快照已变化，请重新预览并审批")
        task.status = ToolTaskStatus.RUNNING.value
        task.started_at = utc_now()
        self.repository.add(ToolExecutionLog(task_id=task.id, stage="EXECUTE", message="开始执行工具任务", details={}))
        await self.repository.commit()
        try:
            result = await self._execute_by_type(task)
            task.status = ToolTaskStatus.SUCCEEDED.value
            task.result_data = result
            task.finished_at = utc_now()
            self.repository.add(
                ToolExecutionLog(
                    task_id=task.id, stage="EXECUTE", message="工具任务执行成功", details={"result": result}
                )
            )
            await self.repository.commit()
        except Exception as exc:
            await self.repository.rollback()
            task = await self.repository.get_task(project_id, task_id, lock=True)
            if task is not None:
                task.status = ToolTaskStatus.FAILED.value
                task.error_message = f"工具执行失败：{type(exc).__name__}"
                task.finished_at = utc_now()
                self.repository.add(
                    ToolExecutionLog(
                        task_id=task.id, stage="EXECUTE", level="ERROR", message=task.error_message, details={}
                    )
                )
                await self.repository.commit()
            raise
        return await self.center_service._task_vo(task, detail=True)

    async def _execute_by_type(self, task: ToolTask) -> dict[str, Any]:
        task_type = ToolTaskType(task.task_type)
        if task_type == ToolTaskType.FILE_GENERATE:
            template = await self.repository.get_template(task.project_id, int(task.input_data["template_id"]))
            if template is None:
                raise NotFoundException("文件模板不存在")
            content, extension, content_type, report = generate_file(template, task.input_data.get("records", []))
            artifact = await self._save_artifact(
                task,
                name=f"{template.name}.{extension}",
                content_type=content_type,
                content=content,
                artifact_type="FILE",
            )
            report_content = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
            report_artifact = await self._save_artifact(
                task,
                name=f"{template.name}-校验报告.json",
                content_type="application/json",
                content=report_content,
                artifact_type="REPORT",
            )
            return {**report, "artifact_ids": [artifact.id, report_artifact.id]}
        if task_type == ToolTaskType.FILE_VALIDATE:
            template = await self.repository.get_template(task.project_id, int(task.input_data["template_id"]))
            artifacts = await self.repository.list_artifacts(task.id)
            artifact = next((item for item in artifacts if item.id == int(task.input_data["input_artifact_id"])), None)
            if template is None or artifact is None:
                raise NotFoundException("模板或输入文件不存在")
            records = parse_file(template, await self._read_artifact(artifact))
            _, errors = validate_records(records, template.fields)
            report = {
                "record_count": len(records),
                "error_count": len(errors),
                "passed": not errors,
                "errors": errors[:10000],
            }
            report_artifact = await self._save_artifact(
                task,
                name=f"{artifact.name}-校验报告.json",
                content_type="application/json",
                content=json.dumps(report, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
                artifact_type="REPORT",
            )
            return {**report, "artifact_ids": [report_artifact.id]}
        if task_type == ToolTaskType.MYSQL_COMPARE:
            return {"comparison": task.preview_data}
        if task_type == ToolTaskType.MYSQL_SYNC:
            target, credentials = await self._connection(
                task.project_id, int(task.input_data["target_connection_id"]), "MYSQL"
            )
            statements = list((task.preview_data or {}).get("sql_statements", []))
            results = await execute_mysql_ddl(target.config, credentials, statements)
            task.rollback_data = {
                "target_connection_id": target.id,
                "rollback_sql_statements": list((task.preview_data or {}).get("rollback_sql_statements", [])),
            }
            return {"executed": results}
        if task_type == ToolTaskType.NACOS_COMPARE:
            return {"comparison": task.preview_data}
        if task_type == ToolTaskType.NACOS_SYNC:
            data = task.input_data
            source, source_credentials = await self._connection(
                task.project_id, int(data["source_connection_id"]), "NACOS"
            )
            target, target_credentials = await self._connection(
                task.project_id, int(data["target_connection_id"]), "NACOS"
            )
            data_id, group, config_type = (
                str(data["data_id"]),
                str(data.get("group", "DEFAULT_GROUP")),
                str(data.get("config_type", "yaml")),
            )
            source_content = await NacosClient(source.config, source_credentials).get_config(data_id, group)
            target_client = NacosClient(target.config, target_credentials)
            target_content = await target_client.get_config(data_id, group)
            if content_hash(target_content) != (task.preview_data or {}).get("target_hash"):
                raise ConflictException("Nacos 目标配置已变化，拒绝发布")
            if content_hash(source_content) != (task.preview_data or {}).get("source_hash"):
                raise ConflictException("Nacos 来源配置已变化，请重新生成预览并审批")
            task.rollback_data = {
                "encrypted_backup": encrypt_secret(target_content),
                "data_id": data_id,
                "group": group,
                "config_type": config_type,
                "target_connection_id": target.id,
            }
            await target_client.publish_config(data_id, group, source_content, config_type)
            return {"published": True, "content_hash": content_hash(source_content), "backup_created": True}
        if task_type == ToolTaskType.DEFECT_SYNC:
            connection, credentials = await self._connection(
                task.project_id,
                int(task.input_data["connection_id"]),
                "DEFECT_PLATFORM",
            )
            # 重新由原始输入构造白名单载荷，而不是信任数据库中可展示的 preview_data。
            return await DefectPlatformClient(connection.config, credentials).create_defect(task.input_data)
        if task_type == ToolTaskType.UI_AUTOMATION:
            connection, _ = await self._connection(
                task.project_id,
                int(task.input_data["connection_id"]),
                "BUSINESS_API",
            )
            spec = UIAutomationSpecDTO.model_validate(
                {
                    "steps": task.input_data.get("steps", []),
                    "variables": task.input_data.get("variables", {}),
                }
            )
            return await execute_playwright_ui(connection.config, spec)
        raise BadRequestException("该工具类型没有执行器")

    async def rollback(self, project_id: int, task_id: int, current_user: User) -> ToolTaskVO:
        task = await self._require_task(project_id, task_id, current_user, lock=True)
        if task.status != ToolTaskStatus.SUCCEEDED.value or not task.rollback_data:
            raise ConflictException("任务没有可用回滚备份")
        if task.task_type == ToolTaskType.NACOS_SYNC.value:
            rollback_data = task.rollback_data
            target, credentials = await self._connection(
                project_id, int(rollback_data["target_connection_id"]), "NACOS"
            )
            await NacosClient(target.config, credentials).publish_config(
                str(rollback_data["data_id"]),
                str(rollback_data["group"]),
                decrypt_secret(str(rollback_data["encrypted_backup"])),
                str(rollback_data["config_type"]),
            )
        elif task.task_type == ToolTaskType.MYSQL_SYNC.value:
            rollback_data = task.rollback_data
            statements = list(rollback_data.get("rollback_sql_statements", []))
            if not statements:
                raise ConflictException("该 MySQL 同步没有可执行的回滚语句")
            target, credentials = await self._connection(
                project_id, int(rollback_data["target_connection_id"]), "MYSQL"
            )
            await execute_mysql_rollback(target.config, credentials, statements)
        else:
            raise BadRequestException("该任务类型不支持回滚")
        task.status = ToolTaskStatus.ROLLED_BACK.value
        task.finished_at = utc_now()
        self.repository.add(
            ToolExecutionLog(task_id=task.id, stage="ROLLBACK", message="已使用执行前备份完成回滚", details={})
        )
        await self.repository.commit()
        return await self.center_service._task_vo(task, detail=True)

    async def get_artifact(
        self,
        project_id: int,
        task_id: int,
        artifact_id: int,
        current_user: User,
    ) -> ToolArtifact:
        """校验项目和任务权限后返回安全产物引用。"""
        await self._require_task(project_id, task_id, current_user)
        artifact = await self.repository.get_artifact(task_id, artifact_id)
        if artifact is None:
            raise NotFoundException("工具产物不存在")
        return artifact
