"""知识问答会话、消息和记忆管理请求模型。"""
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.core.constants import KnowledgeChatSessionStatus
from app.schemas.camel_model import CamelModel
from app.schemas.dto.knowledge_bases import KnowledgeSearchDTO


class KnowledgeChatSessionCreateDTO(CamelModel):
    title: str = Field(default="新会话",min_length=1,max_length=200)



    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: Any) -> Any:
        """去掉会话标题首尾空格；全空格标题会被 min_length 拒绝。"""

        return value.strip() if isinstance(value, str) else value

class KnowledgeChatSessionUpdateDTO(CamelModel):
    title: str | None = Field(default=None,min_length=1,max_length=200)
    status: KnowledgeChatSessionStatus | None = None

    @model_validator(mode="after")
    def reject_empty_or_null_update(self) -> KnowledgeChatSessionUpdateDTO:
        """拒绝空更新，以及把数据库必填字段显式更新成 null。
        model_fields_set 可以理解为“前端实际勾选并提交的字段清单”。
        它不关心字段最终有没有默认值，只记录请求体里出现过哪些字段。
        """

        if not self.model_fields_set:
            raise ValueError("至少提供一个需要更新的字段")

        null_fields = [
            field_name
            for field_name in self.model_fields_set
            if getattr(self, field_name) is None
        ]
        if null_fields:
            names = ", ".join(sorted(null_fields))
            raise ValueError(f"以下字段不能设置为空：{names}")

        return self

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: Any) -> Any:
        """去掉更新标题首尾空格。"""

        return value.strip() if isinstance(value, str) else value

class KnowledgeChatMessageCreateDTO(KnowledgeSearchDTO):
    """
    发送消息 DTO
    """