import json
from typing import Any

from pydantic import Field, field_validator

from app.core.constants import KnowledgeDocumentType
from app.schemas.camel_model import CamelModel


class KnowledgeDocumentUploadDTO(CamelModel):
    """上传知识文档时，除文件二进制之外的业务参数。"""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    document_type: KnowledgeDocumentType
    module_id: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None

    @field_validator("metadata", mode="before")
    @classmethod
    def parse_metadata(cls, value: Any) -> Any:
        """multipart/form-data 中的 JSON 对象会以字符串形式传入。"""

        if value is None or value == "":
            return {}
        if not isinstance(value, str):
            return value

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("metadata 必须是合法的 JSON 对象") from exc

        if not isinstance(parsed, dict):
            raise ValueError("metadata 必须是 JSON 对象")
        return parsed


class KnowledgeDocumentUpdateDTO(CamelModel):
    """编辑文档业务信息；不在这里替换原始文件或手工修改处理状态。"""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    document_type: KnowledgeDocumentType | None = None
    module_id: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value
