"""测试工具中心接口接收的数据结构。"""

from __future__ import annotations

from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from app.core.constants import (
    FileTemplateFormat,
    ToolApprovalDecision,
    ToolConnectionType,
    ToolTaskStatus,
    ToolTaskType,
)
from app.schemas.camel_model import CamelModel


class ExternalConnectionCreateDTO(CamelModel):
    """创建外部连接；credentials 只用于加密写入，不会通过 VO 返回。"""

    name: str = Field(min_length=1, max_length=120)
    connection_type: ToolConnectionType
    config: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class ExternalConnectionUpdateDTO(CamelModel):
    """部分更新连接；不传 credentials 表示保留原密文。"""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    config: dict[str, Any] | None = None
    credentials: dict[str, str] | None = None
    enabled: bool | None = None


class FileTemplateFieldDTO(CamelModel):
    """账务文件中的一个有序字段和生成/校验规则。"""

    name: str = Field(min_length=1, max_length=100)
    source_field: str = Field(min_length=1, max_length=100)
    data_type: str = Field(pattern="^(STRING|INTEGER|DECIMAL|DATE|DATETIME|BOOLEAN)$")
    required: bool = False
    length: int | None = Field(default=None, ge=1, le=10000)
    precision: int | None = Field(default=None, ge=0, le=18)
    format: str | None = Field(default=None, max_length=100)
    padding: str | None = Field(default=None, pattern="^(LEFT|RIGHT)$")
    padding_char: str = Field(default=" ", min_length=1, max_length=1)
    mapping: dict[str, str] = Field(default_factory=dict)
    default_value: Any | None = None

    @model_validator(mode="after")
    def validate_fixed_field(self) -> Self:
        """补位必须同时给出固定长度，金额精度只用于 DECIMAL。"""
        if self.padding is not None and self.length is None:
            raise ValueError("配置补位方向时必须填写字段长度")
        if self.precision is not None and self.data_type != "DECIMAL":
            raise ValueError("precision 只适用于 DECIMAL 字段")
        return self


class FileTemplateCreateDTO(CamelModel):
    """创建可生成、可校验的账务文件模板。"""

    name: str = Field(min_length=1, max_length=120)
    file_format: FileTemplateFormat
    encoding: str = Field(default="UTF-8", pattern="^(UTF-8|GBK)$")
    delimiter: str | None = Field(default=None, min_length=1, max_length=10)
    fields: list[FileTemplateFieldDTO] = Field(min_length=1, max_length=500)
    header_config: dict[str, Any] = Field(default_factory=dict)
    trailer_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("fields")
    @classmethod
    def reject_duplicate_fields(cls, value: list[FileTemplateFieldDTO]) -> list[FileTemplateFieldDTO]:
        names = [field.name for field in value]
        if len(names) != len(set(names)):
            raise ValueError("模板字段名称不能重复")
        return value


class FileTemplateUpdateDTO(CamelModel):
    """整体替换模板可编辑部分，避免字段顺序被局部更新打乱。"""

    name: str = Field(min_length=1, max_length=120)
    file_format: FileTemplateFormat
    encoding: str = Field(default="UTF-8", pattern="^(UTF-8|GBK)$")
    delimiter: str | None = Field(default=None, min_length=1, max_length=10)
    fields: list[FileTemplateFieldDTO] = Field(min_length=1, max_length=500)
    header_config: dict[str, Any] = Field(default_factory=dict)
    trailer_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ToolTaskCreateDTO(CamelModel):
    """创建工具任务；只保存参数，真正执行必须先生成服务器预览。"""

    tool_code: str = Field(min_length=1, max_length=80)
    task_type: ToolTaskType
    title: str = Field(min_length=1, max_length=200)
    input_data: dict[str, Any] = Field(default_factory=dict)


class AIFileRecordsGenerateDTO(CamelModel):
    """根据文件模板生成合成测试数据，而不是要求用户逐字段填写 JSON。"""

    count: int = Field(default=10, ge=1, le=100)
    scenarios: str = Field(default="正常、边界和异常场景均衡覆盖", min_length=1, max_length=1000)
    constraints: str = Field(default="", max_length=4000)


class ToolTaskQueryDTO(CamelModel):
    """工具任务列表筛选。"""

    status: ToolTaskStatus | None = None
    task_type: ToolTaskType | None = None
    current: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class ToolApprovalDTO(CamelModel):
    """审批人对当前预览快照作出决定。"""

    decision: ToolApprovalDecision
    comment: str = Field(default="", max_length=2000)
