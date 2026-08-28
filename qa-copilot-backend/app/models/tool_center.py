"""测试工具中心、外部连接、审批、执行日志和文件模板实体。"""

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


class ToolDefinition(TimestampMixin, Base):
    """平台注册的工具能力，不保存可执行代码。"""

    __tablename__ = "tool_definitions"
    __table_args__ = (
        CheckConstraint("risk_level IN ('LOW','MEDIUM','HIGH')", name="chk_tool_definitions_risk"),
        {"comment": "可在受控执行器中使用的工具目录"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="工具主键")
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, comment="稳定工具编码")
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="工具中文名称")
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''"), comment="工具用途说明"
    )
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, comment="风险等级")
    required_permission: Mapped[str] = mapped_column(String(120), nullable=False, comment="执行所需权限码")
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), comment="是否允许创建新任务"
    )


class ExternalConnection(TimestampMixin, Base):
    """项目级外部系统连接；公开配置与加密凭据分离保存。"""

    __tablename__ = "external_connections"
    __table_args__ = (
        CheckConstraint(
            "connection_type IN ('MYSQL','NACOS','BUSINESS_API','DEFECT_PLATFORM')",
            name="chk_external_connections_type",
        ),
        UniqueConstraint("project_id", "name", name="uq_external_connections_project_name"),
        Index("ix_external_connections_project_type", "project_id", "connection_type"),
        {"comment": "MySQL、Nacos、业务接口和缺陷平台连接"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="连接主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"), nullable=False, comment="所属项目"
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="连接名称")
    connection_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="外部系统类型")
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), comment="不含密码和令牌的连接配置"
    )
    encrypted_credentials: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''"), comment="DATA_ENCRYPTION_KEY 加密后的凭据 JSON"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), comment="是否允许工具任务使用"
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="创建用户"
    )


class ToolTask(TimestampMixin, Base):
    """一次工具预览、审批、执行和回滚的业务主记录。"""

    __tablename__ = "tool_tasks"
    __table_args__ = (
        CheckConstraint("risk_level IN ('LOW','MEDIUM','HIGH')", name="chk_tool_tasks_risk"),
        CheckConstraint(
            "status IN ('DRAFT','PREVIEWED','PENDING_APPROVAL','APPROVED',"
            "'REJECTED','RUNNING','SUCCEEDED','FAILED','ROLLED_BACK',"
            "'CANCELLED')",
            name="chk_tool_tasks_status",
        ),
        Index("ix_tool_tasks_project_status", "project_id", "status", "id"),
        {"comment": "工具任务及完整状态机"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="工具任务主键")
    project_id: Mapped[int] = mapped_column(
        ForeignKey("test_projects.id", ondelete="CASCADE"), nullable=False, comment="数据隔离项目"
    )
    tool_id: Mapped[int] = mapped_column(
        ForeignKey("tool_definitions.id", ondelete="RESTRICT"), nullable=False, comment="使用的工具"
    )
    task_type: Mapped[str] = mapped_column(String(40), nullable=False, comment="具体业务任务类型")
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="任务标题")
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, comment="创建时冻结的风险等级")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", server_default=text("'DRAFT'"), comment="任务当前状态"
    )
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="请求人"
    )
    input_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), comment="脱敏后的执行输入"
    )
    preview_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, comment="只读预览结果")
    preview_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="规范化预览 SHA-256，用于执行前复核"
    )
    result_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, comment="执行结果摘要")
    rollback_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, comment="回滚备份及结果摘要")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="脱敏失败摘要")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="开始执行时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="执行结束时间")

    tool: Mapped[ToolDefinition] = relationship("ToolDefinition", lazy="selectin")


class ToolApproval(TimestampMixin, Base):
    """工具任务人工审批记录；每次决定都保留，不覆盖历史。"""

    __tablename__ = "tool_approvals"
    __table_args__ = ({"comment": "高风险工具任务审批审计"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tool_tasks.id", ondelete="CASCADE"), nullable=False, index=True, comment="工具任务"
    )
    requester_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="请求人快照"
    )
    approver_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="审批人"
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False, comment="APPROVED 或 REJECTED")
    comment: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''"), comment="审批意见"
    )
    preview_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="审批时确认的预览哈希")


class ToolExecutionLog(TimestampMixin, Base):
    """工具任务不可变阶段日志。"""

    __tablename__ = "tool_execution_logs"
    __table_args__ = (
        Index("ix_tool_execution_logs_task_id", "task_id", "id"),
        {"comment": "工具任务阶段与异常审计日志"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tool_tasks.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False, comment="PREVIEW、APPROVE、EXECUTE 或 ROLLBACK")
    level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INFO", server_default=text("'INFO'"), comment="日志级别"
    )
    message: Mapped[str] = mapped_column(Text, nullable=False, comment="脱敏日志正文")
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), comment="结构化补充信息"
    )


class ToolArtifact(TimestampMixin, Base):
    """工具生成文件、报告、快照或备份的安全引用。"""

    __tablename__ = "tool_artifacts"
    __table_args__ = (
        Index("ix_tool_artifacts_task", "task_id", "id"),
        {"comment": "工具任务生成的文件、报告和回滚备份"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tool_tasks.id", ondelete="CASCADE"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(40), nullable=False, comment="FILE、REPORT、SNAPSHOT 或 BACKUP")
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="产物名称")
    object_key: Mapped[str] = mapped_column(String(1000), nullable=False, comment="对象存储键，不直接返回前端")
    content_type: Mapped[str] = mapped_column(String(160), nullable=False, comment="媒体类型")
    size_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"), comment="产物字节数"
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, comment="完整性哈希")


class FileTemplate(TimestampMixin, Base):
    """项目级账务文件结构模板。"""

    __tablename__ = "file_templates"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_file_templates_project_name"),
        CheckConstraint(
            "file_format IN ('CSV','EXCEL','FIXED_WIDTH_TXT','DELIMITED_TXT','JSON','XML')",
            name="chk_file_templates_format",
        ),
        Index("ix_file_templates_project", "project_id", "id"),
        {"comment": "账务文件字段、格式和校验规则模板"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("test_projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="模板名称")
    file_format: Mapped[str] = mapped_column(String(30), nullable=False, comment="CSV、Excel、TXT、JSON 或 XML")
    encoding: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UTF-8", server_default=text("'UTF-8'"), comment="文本文件编码"
    )
    delimiter: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="分隔符文本格式使用")
    fields: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
        comment="有序字段及类型、长度、格式、补位、映射和校验规则",
    )
    header_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), comment="文件头配置"
    )
    trailer_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), comment="文件尾、总笔数和总金额配置"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
