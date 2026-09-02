"""测试环境自然语言数据查询的业务编排。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.exc import IntegrityError

from app.agents.data_query_graph import DATA_QUERY_GRAPH, DataQueryGraphContext
from app.core.config import settings
from app.core.constants import (
    AIModelTaskType,
    DataQueryExecutionStatus,
    DataSourceDatabaseType,
    TestEnvironmentType,
)
from app.core.security import decrypt_secret, encrypt_secret
from app.data_query.adapters import DataSourceAdapter, create_data_source_adapter
from app.data_query.sql_security import SQLSafetyValidator
from app.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    InternalServerException,
    NotFoundException,
)
from app.exceptions.errors import describe_exception
from app.exceptions.exception_base import BusinessException
from app.models import DataQueryExecution, DataSourceMetadataSnapshot, EnvironmentDataSource, User
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.data_query_repository import DataQueryRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.api_result import PageResult
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.schemas.dto.data_query import (
    DataQueryExecuteDTO,
    DataQuerySummaryPayload,
    EnvironmentDataSourceCreateDTO,
    EnvironmentDataSourceUpdateDTO,
)
from app.schemas.vo.data_query import (
    DataQueryExecutionVO,
    DataSourceConnectionResultVO,
    DataSourceMetadataVO,
    EnvironmentDataSourceVO,
)
from app.utils.ai_client_util import generate_text_with_langchain


class DataQueryService:
    """协调平台权限、模型生成、SQL 安全校验和异构数据库只读执行。"""

    def __init__(
        self,
        repository: DataQueryRepository,
        project_repository: TestProjectsRepository,
        ai_model_repository: AIModelRepository,
        prompt_template_repository: PromptTemplateRepository,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.ai_model_repository = ai_model_repository
        self.prompt_template_repository = prompt_template_repository
        self.validator = SQLSafetyValidator()

    async def _require_project(self, project_id: int, current_user: User) -> None:
        """同时校验项目是否存在，以及登录用户是否属于该项目。"""
        if await self.project_repository.get_accessible_project(project_id, current_user) is None:
            raise NotFoundException("项目不存在或当前用户无权访问")

    async def _require_environment(self, project_id: int, environment_id: int) -> None:
        """校验环境归属，并强制阻断生产环境数据查询。"""
        environment = await self.repository.get_project_environment(project_id, environment_id)
        if environment is None:
            raise NotFoundException("测试环境不存在")
        if environment.environment_type == TestEnvironmentType.PRODUCTION.value:
            raise ForbiddenException("智能数据查询仅允许连接非生产环境")

    @staticmethod
    def _source_config(payload: EnvironmentDataSourceCreateDTO | EnvironmentDataSourceUpdateDTO) -> dict[str, Any]:
        """把非密钥连接选项转换成可安全落库的 JSON。"""
        values = payload.model_dump(exclude_unset=True)
        return {
            key: values[key]
            for key in ("ssl_enabled", "charset", "allowed_tables", "sensitive_columns")
            if key in values
        }

    @staticmethod
    def _encrypt_credentials(username: str, password: str) -> str:
        """用户名和密码统一序列化后使用平台数据密钥加密。"""
        return encrypt_secret(json.dumps({"username": username, "password": password}, ensure_ascii=False))

    @staticmethod
    def _decrypt_credentials(source: EnvironmentDataSource) -> dict[str, str]:
        """仅在连接数据库前于内存中解密凭据，不写日志也不返回前端。"""
        try:
            value = json.loads(decrypt_secret(source.encrypted_credentials))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise InternalServerException("数据源凭据无法解密，请重新配置") from exc
        if not isinstance(value, dict):
            raise InternalServerException("数据源凭据格式错误，请重新配置")
        return {"username": str(value.get("username", "")), "password": str(value.get("password", ""))}

    @staticmethod
    def _adapter_config(source: EnvironmentDataSource) -> dict[str, Any]:
        """组合公开连接字段与 JSON 配置，交给统一数据库适配器。"""
        return {
            "host": source.host,
            "port": source.port,
            "database_name": source.database_name,
            "schema_name": source.schema_name,
            **(source.config or {}),
        }

    def _adapter(self, source: EnvironmentDataSource) -> DataSourceAdapter:
        return create_data_source_adapter(
            DataSourceDatabaseType(source.database_type),
            self._adapter_config(source),
            self._decrypt_credentials(source),
            settings.data_query_default_timeout_seconds,
        )

    async def _source_read(self, source: EnvironmentDataSource) -> EnvironmentDataSourceVO:
        metadata = await self.repository.get_metadata(source.id)
        config = source.config or {}
        return EnvironmentDataSourceVO(
            id=source.id,
            project_id=source.project_id,
            environment_id=source.environment_id,
            name=source.name,
            database_type=DataSourceDatabaseType(source.database_type),
            host=source.host,
            port=source.port,
            database_name=source.database_name,
            schema_name=source.schema_name,
            ssl_enabled=bool(config.get("ssl_enabled", False)),
            charset=str(config.get("charset") or "utf8mb4"),
            allowed_tables=list(config.get("allowed_tables") or []),
            sensitive_columns=dict(config.get("sensitive_columns") or {}),
            credentials_configured=bool(source.encrypted_credentials),
            enabled=source.enabled,
            metadata_table_count=metadata.table_count if metadata else 0,
            metadata_captured_at=metadata.captured_at if metadata else None,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )

    @staticmethod
    def _execution_read(execution: DataQueryExecution) -> DataQueryExecutionVO:
        source_name = (
            execution.data_source.name
            if execution.data_source is not None
            else f"数据源#{execution.data_source_id}"
        )
        return DataQueryExecutionVO(
            id=execution.id,
            project_id=execution.project_id,
            environment_id=execution.environment_id,
            data_source_id=execution.data_source_id,
            data_source_name=source_name,
            user_id=execution.user_id,
            question=execution.question,
            status=DataQueryExecutionStatus(execution.status),
            sql_dialect=execution.sql_dialect,
            generated_sql=execution.generated_sql,
            parameters=execution.parameters or {},
            referenced_tables=execution.referenced_tables or [],
            validation_errors=execution.validation_errors or [],
            result_columns=execution.result_columns or [],
            result_rows=execution.result_rows or [],
            result_row_count=execution.result_row_count,
            truncated=execution.truncated,
            summary=execution.summary,
            visualization=execution.visualization or {},
            estimated_rows=execution.estimated_rows,
            full_table_scan=execution.full_table_scan,
            latency_ms=execution.latency_ms,
            error_message=execution.error_message,
            created_at=execution.created_at,
            updated_at=execution.updated_at,
        )

    async def list_sources(
        self, project_id: int, environment_id: int | None, current_user: User
    ) -> list[EnvironmentDataSourceVO]:
        await self._require_project(project_id, current_user)
        if environment_id is not None:
            await self._require_environment(project_id, environment_id)
        sources = await self.repository.list_sources(project_id, environment_id)
        return [await self._source_read(source) for source in sources]

    async def create_source(
        self, project_id: int, payload: EnvironmentDataSourceCreateDTO, current_user: User
    ) -> EnvironmentDataSourceVO:
        await self._require_project(project_id, current_user)
        await self._require_environment(project_id, payload.environment_id)
        source = EnvironmentDataSource(
            project_id=project_id,
            environment_id=payload.environment_id,
            name=payload.name,
            database_type=payload.database_type.value,
            host=payload.host,
            port=payload.port,
            database_name=payload.database_name,
            schema_name=payload.schema_name,
            config=self._source_config(payload),
            encrypted_credentials=self._encrypt_credentials(payload.username, payload.password),
            enabled=payload.enabled,
            created_by=current_user.id,
        )
        self.repository.add(source)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("该测试环境已存在同名数据源") from exc
        await self.repository.refresh(source)
        return await self._source_read(source)

    async def update_source(
        self,
        project_id: int,
        source_id: int,
        payload: EnvironmentDataSourceUpdateDTO,
        current_user: User,
    ) -> EnvironmentDataSourceVO:
        await self._require_project(project_id, current_user)
        source = await self.repository.get_source(project_id, source_id)
        if source is None:
            raise NotFoundException("环境数据源不存在")
        changes = payload.model_dump(exclude_unset=True)
        old_credentials = self._decrypt_credentials(source)
        username = changes.pop("username", None)
        password = changes.pop("password", None)
        config_keys = {"ssl_enabled", "charset", "allowed_tables", "sensitive_columns"}
        config_changes = {
            key: changes.pop(key)
            for key in list(changes)
            if key in config_keys
        }
        for key, value in changes.items():
            setattr(source, key, value)
        if config_changes:
            source.config = {**(source.config or {}), **config_changes}
        if username is not None or password is not None:
            source.encrypted_credentials = self._encrypt_credentials(
                username if username is not None else old_credentials["username"],
                password if password is not None else old_credentials["password"],
            )
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("该测试环境已存在同名数据源") from exc
        await self.repository.refresh(source)
        return await self._source_read(source)

    async def delete_source(self, project_id: int, source_id: int, current_user: User) -> None:
        await self._require_project(project_id, current_user)
        source = await self.repository.get_source(project_id, source_id)
        if source is None:
            raise NotFoundException("环境数据源不存在")
        await self.repository.delete(source)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("该数据源已有查询审计记录，请停用而不是删除") from exc

    async def test_source(
        self, project_id: int, source_id: int, current_user: User
    ) -> DataSourceConnectionResultVO:
        await self._require_project(project_id, current_user)
        source = await self.repository.get_source(project_id, source_id)
        if source is None:
            raise NotFoundException("环境数据源不存在")
        result = await self._adapter(source).test_connection()
        return DataSourceConnectionResultVO(
            success=True,
            database_version=result.database_version,
            latency_ms=result.latency_ms,
            message="数据库连接成功；仍建议在数据库端使用仅 SELECT 账号",
        )

    async def refresh_metadata(
        self, project_id: int, source_id: int, current_user: User
    ) -> DataSourceMetadataVO:
        await self._require_project(project_id, current_user)
        source = await self.repository.get_source(project_id, source_id)
        if source is None:
            raise NotFoundException("环境数据源不存在")
        metadata_json = await self._adapter(source).introspect_metadata(settings.data_query_max_metadata_tables)
        captured_at = datetime.now(UTC)
        snapshot = await self.repository.get_metadata_for_update(source.id)
        if snapshot is None:
            snapshot = DataSourceMetadataSnapshot(
                data_source_id=source.id,
                metadata_json=metadata_json,
                table_count=len(metadata_json.get("tables", [])),
                captured_at=captured_at,
            )
            self.repository.add(snapshot)
        else:
            snapshot.metadata_json = metadata_json
            snapshot.table_count = len(metadata_json.get("tables", []))
            snapshot.captured_at = captured_at
        await self.repository.commit()
        return DataSourceMetadataVO(
            data_source_id=source.id,
            database_type=DataSourceDatabaseType(source.database_type),
            database_name=source.database_name,
            schema_name=source.schema_name,
            tables=metadata_json.get("tables", []),
            table_count=len(metadata_json.get("tables", [])),
            captured_at=captured_at,
        )

    async def get_metadata(
        self, project_id: int, source_id: int, current_user: User
    ) -> DataSourceMetadataVO:
        await self._require_project(project_id, current_user)
        source = await self.repository.get_source(project_id, source_id)
        if source is None:
            raise NotFoundException("环境数据源不存在")
        snapshot = await self.repository.get_metadata(source.id)
        if snapshot is None:
            return await self.refresh_metadata(project_id, source_id, current_user)
        return DataSourceMetadataVO(
            data_source_id=source.id,
            database_type=DataSourceDatabaseType(source.database_type),
            database_name=source.database_name,
            schema_name=source.schema_name,
            tables=snapshot.metadata_json.get("tables", []),
            table_count=snapshot.table_count,
            captured_at=snapshot.captured_at,
        )

    @staticmethod
    def _filtered_schema(source: EnvironmentDataSource, metadata: DataSourceMetadataVO) -> tuple[str, set[str]]:
        """只把允许查询的表结构发送给模型，减少 Token 与越权幻觉。"""
        configured = {str(name).lower() for name in (source.config or {}).get("allowed_tables", [])}
        tables = [
            table
            for table in metadata.tables
            if not configured or str(table.get("name", "")).lower() in configured
        ]
        allowed = {str(table.get("name", "")) for table in tables if table.get("name")}
        return json.dumps({"tables": tables}, ensure_ascii=False, separators=(",", ":")), allowed

    async def _load_ai_configuration(self):
        model = await self.ai_model_repository.get_default_model()
        if model is None or not model.enabled or model.provider is None or not model.provider.enabled:
            raise InternalServerException("默认 AI 模型或服务商未启用")
        if AIModelTaskType.DATA_QUERY.value not in (model.task_types or []):
            raise InternalServerException("默认模型不支持智能数据查询，请为模型勾选“数据查询”任务类型")
        sql_prompt = await self.prompt_template_repository.get_by_code("data_query_sql")
        summary_prompt = await self.prompt_template_repository.get_by_code("data_query_summary")
        if sql_prompt is None or not sql_prompt.enabled:
            raise InternalServerException("智能数据查询 SQL Prompt 未配置或已停用")
        if summary_prompt is None or not summary_prompt.enabled:
            raise InternalServerException("智能数据查询总结 Prompt 未配置或已停用")
        return model, sql_prompt, summary_prompt

    @staticmethod
    def _trim_result_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
        """按序保留能放进平台审计字段的结果，防止宽字段撑爆响应和 JSONB。"""
        accepted: list[dict[str, Any]] = []
        total_bytes = 2
        for row in rows:
            row_bytes = len(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8")) + 1
            if total_bytes + row_bytes > settings.data_query_max_result_bytes:
                return accepted, True
            accepted.append(row)
            total_bytes += row_bytes
        return accepted, False

    async def _summarize(
        self,
        *,
        execution: DataQueryExecution,
        model,
        prompt_template,
        request_id: str,
    ) -> DataQuerySummaryPayload:
        """把表格结果转换成产品人员可读的结论；失败时退化为确定性说明。"""
        if not execution.result_rows:
            return DataQuerySummaryPayload(summary="查询成功，但当前条件下没有匹配数据。")
        prompt = ChatPromptTemplate.from_messages(
            [("system", prompt_template.system_prompt), ("human", prompt_template.user_prompt)]
        )
        try:
            result = await generate_text_with_langchain(
                repository=self.ai_model_repository,
                provider=model.provider,
                model=model,
                chat_prompt=prompt,
                input_variables={
                    "question": execution.question,
                    "sql": execution.generated_sql or "",
                    "result_json": json.dumps(execution.result_rows[:100], ensure_ascii=False, default=str),
                    "output_schema": json.dumps(DataQuerySummaryPayload.model_json_schema(), ensure_ascii=False),
                },
                task_type=AIModelTaskType.DATA_QUERY.value,
                reasoning_effort="minimal",
                usage_context=AIUsageContextDTO(
                    request_id=request_id,
                    user_id=execution.user_id,
                    project_id=execution.project_id,
                    task_id=f"data-query:{execution.id}",
                ),
            )
            text = result.content.strip()
            if text.startswith("```"):
                text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return DataQuerySummaryPayload.model_validate_json(text)
        except Exception:
            return DataQuerySummaryPayload(summary=f"查询成功，共返回 {execution.result_row_count} 条数据。")

    async def execute_query(
        self,
        project_id: int,
        payload: DataQueryExecuteDTO,
        current_user: User,
        request_id: str,
    ) -> DataQueryExecutionVO:
        """完成“自然语言 → SQL → 校验 → 执行 → 总结”的整条受控链路。"""
        await self._require_project(project_id, current_user)
        await self._require_environment(project_id, payload.environment_id)
        source = await self.repository.get_source(project_id, payload.data_source_id)
        if source is None or source.environment_id != payload.environment_id:
            raise NotFoundException("当前测试环境中不存在该数据源")
        if not source.enabled:
            raise BadRequestException("环境数据源已停用")

        execution = DataQueryExecution(
            project_id=project_id,
            environment_id=payload.environment_id,
            data_source_id=source.id,
            user_id=current_user.id,
            question=payload.question,
            status=DataQueryExecutionStatus.GENERATING.value,
            sql_dialect=source.database_type,
            data_source=source,
        )
        self.repository.add(execution)
        await self.repository.commit()
        await self.repository.refresh(execution)

        try:
            metadata = await self.get_metadata(project_id, source.id, current_user)
            schema_context, allowed_tables = self._filtered_schema(source, metadata)
            if not allowed_tables:
                raise BadRequestException("数据源没有可供查询的表，请刷新元数据或检查表白名单")
            model, sql_prompt, summary_prompt = await self._load_ai_configuration()
            execution.status = DataQueryExecutionStatus.VALIDATING.value
            graph_result = await DATA_QUERY_GRAPH.ainvoke(
                {
                    "question": payload.question,
                    "retry_count": 0,
                    "max_retries": settings.data_query_max_generation_retries,
                },
                context=DataQueryGraphContext(
                    ai_model_repository=self.ai_model_repository,
                    ai_model=model,
                    prompt_template=sql_prompt,
                    usage_context=AIUsageContextDTO(
                        request_id=request_id,
                        user_id=current_user.id,
                        project_id=project_id,
                        task_id=f"data-query:{execution.id}",
                    ),
                    database_type=DataSourceDatabaseType(source.database_type),
                    database_name=source.database_name,
                    schema_context=schema_context,
                    allowed_tables=allowed_tables,
                    sensitive_columns={
                        str(table): {str(column) for column in columns}
                        for table, columns in (source.config or {}).get("sensitive_columns", {}).items()
                    },
                    max_rows=settings.data_query_default_row_limit,
                    max_retries=settings.data_query_max_generation_retries,
                    validator=self.validator,
                ),
            )
            generated = graph_result.get("generated_payload")
            if generated is None:
                execution.status = DataQueryExecutionStatus.REJECTED.value
                execution.validation_errors = list(graph_result.get("validation_errors") or [])
                execution.error_message = "模型多次生成的 SQL 均未通过安全校验"
                await self.repository.commit()
                raise BadRequestException(execution.error_message)

            execution.generated_sql = str(graph_result["normalized_sql"])
            execution.parameters = generated.parameters
            execution.referenced_tables = list(graph_result.get("referenced_tables") or [])
            adapter = self._adapter(source)
            plan = await adapter.explain(execution.generated_sql, execution.parameters)
            execution.estimated_rows = plan.estimated_rows
            execution.full_table_scan = plan.full_table_scan
            if plan.estimated_rows is not None and plan.estimated_rows > settings.data_query_explain_row_threshold:
                execution.status = DataQueryExecutionStatus.REJECTED.value
                execution.validation_errors = [f"查询计划预计扫描 {plan.estimated_rows} 行，超过平台安全阈值"]
                execution.error_message = execution.validation_errors[0]
                await self.repository.commit()
                raise BadRequestException(execution.error_message)

            execution.status = DataQueryExecutionStatus.EXECUTING.value
            result = await adapter.execute(
                execution.generated_sql,
                execution.parameters,
                settings.data_query_default_row_limit,
            )
            execution.result_columns = result.columns
            execution.result_rows, byte_truncated = self._trim_result_rows(result.rows)
            execution.result_row_count = len(execution.result_rows)
            execution.truncated = result.truncated or byte_truncated
            execution.latency_ms = result.latency_ms
            summary = await self._summarize(
                execution=execution,
                model=model,
                prompt_template=summary_prompt,
                request_id=request_id,
            )
            execution.summary = summary.summary
            execution.visualization = {
                "chartType": summary.chart_type,
                "xField": summary.x_field,
                "yField": summary.y_field,
                "insights": summary.insights,
            }
            execution.status = DataQueryExecutionStatus.SUCCEEDED.value
            await self.repository.commit()
            await self.repository.refresh(execution)
            execution.data_source = source
            return self._execution_read(execution)
        except BusinessException as exc:
            if execution.status not in {
                DataQueryExecutionStatus.REJECTED.value,
                DataQueryExecutionStatus.SUCCEEDED.value,
            }:
                execution.status = DataQueryExecutionStatus.FAILED.value
                execution.error_message = execution.error_message or describe_exception(exc)[:2000]
                await self.repository.commit()
            raise
        except Exception as exc:
            execution.status = DataQueryExecutionStatus.FAILED.value
            execution.error_message = describe_exception(exc)[:2000]
            await self.repository.commit()
            raise InternalServerException("智能数据查询执行失败，请在查询历史中查看原因") from exc

    async def list_history(
        self,
        project_id: int,
        current_user: User,
        environment_id: int | None,
        source_id: int | None,
        current: int,
        size: int,
    ) -> PageResult[DataQueryExecutionVO]:
        await self._require_project(project_id, current_user)
        records, total = await self.repository.list_history(project_id, environment_id, source_id, current, size)
        return PageResult(
            current=current,
            size=size,
            total=total,
            records=[self._execution_read(record) for record in records],
        )

    async def get_execution(
        self, project_id: int, execution_id: int, current_user: User
    ) -> DataQueryExecutionVO:
        await self._require_project(project_id, current_user)
        execution = await self.repository.get_execution(project_id, execution_id)
        if execution is None:
            raise NotFoundException("智能数据查询记录不存在")
        return self._execution_read(execution)
