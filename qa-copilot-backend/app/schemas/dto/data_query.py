"""智能数据查询接口接收的数据结构。"""

from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from app.core.constants import DataSourceDatabaseType
from app.schemas.camel_model import CamelModel


class EnvironmentDataSourceCreateDTO(CamelModel):
    """创建测试环境数据源；密码只用于加密入库。"""

    environment_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    database_type: DataSourceDatabaseType
    host: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database_name: str = Field(min_length=1, max_length=128)
    schema_name: str | None = Field(default=None, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(max_length=1000)
    ssl_enabled: bool = False
    charset: str = Field(default="utf8mb4", min_length=1, max_length=40)
    allowed_tables: list[str] = Field(default_factory=list, max_length=2000)
    sensitive_columns: dict[str, list[str]] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("name", "host", "database_name", "username", "schema_name", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("allowed_tables")
    @classmethod
    def normalize_allowed_tables(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("允许查询的表不能重复")
        return normalized

    @model_validator(mode="after")
    def apply_database_defaults(self) -> Self:
        if self.port is None:
            self.port = 3306 if self.database_type is DataSourceDatabaseType.MYSQL else 5432
        if self.database_type is DataSourceDatabaseType.POSTGRESQL and not self.schema_name:
            self.schema_name = "public"
        if self.database_type is DataSourceDatabaseType.MYSQL:
            self.schema_name = None
        return self


class EnvironmentDataSourceUpdateDTO(CamelModel):
    """编辑数据源；用户名或密码不传时保留原加密凭据。"""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database_name: str | None = Field(default=None, min_length=1, max_length=128)
    schema_name: str | None = Field(default=None, max_length=128)
    username: str | None = Field(default=None, min_length=1, max_length=128)
    password: str | None = Field(default=None, max_length=1000)
    ssl_enabled: bool | None = None
    charset: str | None = Field(default=None, min_length=1, max_length=40)
    allowed_tables: list[str] | None = Field(default=None, max_length=2000)
    sensitive_columns: dict[str, list[str]] | None = None
    enabled: bool | None = None

    @field_validator("name", "host", "database_name", "username", "schema_name", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class DataQueryExecuteDTO(CamelModel):
    """把自然语言问题提交给指定测试环境数据源。"""

    environment_id: int = Field(gt=0)
    data_source_id: int = Field(gt=0)
    question: str = Field(min_length=2, max_length=2000)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        return value.strip()


class DataQueryHistoryQueryDTO(CamelModel):
    """查询项目内的智能数据查询历史。"""

    environment_id: int | None = Field(default=None, gt=0)
    data_source_id: int | None = Field(default=None, gt=0)
    current: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class GeneratedSQLPayload(CamelModel):
    """大语言模型必须返回的结构化 SQL 草稿。"""

    title: str = Field(default="数据查询", max_length=120)
    sql: str = Field(min_length=1, max_length=50000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list, max_length=20)


class DataQuerySummaryPayload(CamelModel):
    """模型对有限查询结果生成的结构化说明。"""

    summary: str = Field(min_length=1, max_length=5000)
    chart_type: str = Field(default="NONE", pattern="^(NONE|BAR|LINE|PIE)$")
    x_field: str | None = Field(default=None, max_length=128)
    y_field: str | None = Field(default=None, max_length=128)
    insights: list[str] = Field(default_factory=list, max_length=10)
