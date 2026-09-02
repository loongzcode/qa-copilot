"""测试环境数据源、元数据快照和智能查询执行记录。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class EnvironmentDataSource(TimestampMixin, Base):
    """测试环境中的一个可查询数据库连接。

    公开连接参数与账号密码分开保存；凭据只以 Fernet 密文落库，接口返回时
    仅说明是否已经配置，永远不返回明文。
    """

    __tablename__ = "environment_data_sources"
    __table_args__ = (
        CheckConstraint("database_type IN ('MYSQL','POSTGRESQL')", name="chk_environment_data_sources_type"),
        UniqueConstraint("environment_id", "name", name="uq_environment_data_sources_environment_name"),
        Index("ix_environment_data_sources_project_environment", "project_id", "environment_id", "enabled"),
        {"comment": "测试环境下供智能数据查询使用的只读数据库连接"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="数据源主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"), nullable=False, comment="所属项目"
    )
    environment_id: Mapped[int] = mapped_column(
        ForeignKey("test_environments.id", ondelete="CASCADE"), nullable=False, comment="所属测试环境"
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="数据源名称")
    database_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="MYSQL 或 POSTGRESQL")
    host: Mapped[str] = mapped_column(String(255), nullable=False, comment="数据库主机名或 IP")
    port: Mapped[int] = mapped_column(Integer, nullable=False, comment="数据库端口")
    database_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="数据库名称")
    schema_name: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="PostgreSQL Schema")
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="SSL、字符集、表白名单和敏感字段等非密钥配置",
    )
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False, comment="加密后的用户名和密码 JSON")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="创建用户"
    )


class DataSourceMetadataSnapshot(TimestampMixin, Base):
    """数据源最近一次结构快照，供模型选择表和字段。"""

    __tablename__ = "data_source_metadata_snapshots"
    __table_args__ = (
        UniqueConstraint("data_source_id", name="uq_data_source_metadata_snapshots_source"),
        {"comment": "表、字段、主外键、索引和注释的规范化快照"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_source_id: Mapped[int] = mapped_column(
        ForeignKey("environment_data_sources.id", ondelete="CASCADE"), nullable=False, comment="数据源主键"
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), comment="规范化数据库结构"
    )
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="快照采集时间")


class DataQueryExecution(TimestampMixin, Base):
    """一次自然语言生成、校验并执行只读 SQL 的完整审计记录。"""

    __tablename__ = "data_query_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('GENERATING','VALIDATING','EXECUTING','SUCCEEDED','REJECTED','FAILED')",
            name="chk_data_query_executions_status",
        ),
        Index("ix_data_query_executions_project_user", "project_id", "user_id", "id"),
        Index("ix_data_query_executions_source_created", "data_source_id", "created_at"),
        {"comment": "智能数据查询 SQL、结果摘要、风险和失败原因审计"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("test_projects.id", ondelete="CASCADE"), nullable=False)
    environment_id: Mapped[int] = mapped_column(ForeignKey("test_environments.id", ondelete="CASCADE"), nullable=False)
    data_source_id: Mapped[int] = mapped_column(
        ForeignKey("environment_data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False, comment="产品人员输入的自然语言问题")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="GENERATING", server_default=text("'GENERATING'")
    )
    sql_dialect: Mapped[str] = mapped_column(String(20), nullable=False)
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True, comment="实际通过校验并执行的 SQL")
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), comment="绑定查询参数"
    )
    referenced_tables: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    validation_errors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    result_columns: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    result_rows: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    result_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    visualization: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    estimated_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    full_table_scan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="脱敏后的失败原因")

    data_source: Mapped[EnvironmentDataSource] = relationship("EnvironmentDataSource", lazy="selectin")
