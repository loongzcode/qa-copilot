"""智能数据查询接口返回的数据结构。"""

from datetime import datetime
from typing import Any

from app.core.constants import DataQueryExecutionStatus, DataSourceDatabaseType
from app.schemas.camel_model import CamelModel


class EnvironmentDataSourceVO(CamelModel):
    """脱敏后的环境数据源。"""

    id: int
    project_id: int
    environment_id: int
    name: str
    database_type: DataSourceDatabaseType
    host: str
    port: int
    database_name: str
    schema_name: str | None
    ssl_enabled: bool
    charset: str
    allowed_tables: list[str]
    sensitive_columns: dict[str, list[str]]
    credentials_configured: bool
    enabled: bool
    metadata_table_count: int = 0
    metadata_captured_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DataSourceConnectionResultVO(CamelModel):
    """数据源连接和只读权限测试结果。"""

    success: bool
    database_version: str
    latency_ms: int
    message: str


class DataSourceMetadataVO(CamelModel):
    """供页面查看和 Agent 使用的数据库结构快照。"""

    data_source_id: int
    database_type: DataSourceDatabaseType
    database_name: str
    schema_name: str | None
    tables: list[dict[str, Any]]
    table_count: int
    captured_at: datetime


class DataQueryExecutionVO(CamelModel):
    """一次查询的 SQL、风险分析、结果和自然语言总结。"""

    id: int
    project_id: int
    environment_id: int
    data_source_id: int
    data_source_name: str
    user_id: int | None
    question: str
    status: DataQueryExecutionStatus
    sql_dialect: str
    generated_sql: str | None
    parameters: dict[str, Any]
    referenced_tables: list[str]
    validation_errors: list[str]
    result_columns: list[str]
    result_rows: list[dict[str, Any]]
    result_row_count: int
    truncated: bool
    summary: str
    visualization: dict[str, Any]
    estimated_rows: int | None
    full_table_scan: bool
    latency_ms: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime
