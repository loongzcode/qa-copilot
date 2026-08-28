from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas.camel_model import CamelModel


class PromptTemplateCreateDTO(CamelModel):
    """创建 Prompt 模板时接收的参数。"""

    # code 是程序引用模板时使用的稳定业务编码，创建后不允许修改。
    code: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="小写字母开头，只能包含小写字母、数字和下划线",
    )
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
    enabled: bool = True

    @field_validator("code", "name", "description", mode="before")
    @classmethod
    def strip_short_text(cls, value: Any) -> Any:
        """去掉短文本首尾空格，再执行长度和格式校验。"""

        return value.strip() if isinstance(value, str) else value

    @field_validator("system_prompt", "user_prompt", mode="before")
    @classmethod
    def reject_blank_prompt(cls, value: Any) -> Any:
        """Prompt 可以保留原有排版，但不能只包含空白字符。"""

        if isinstance(value, str) and not value.strip():
            return ""
        return value


class PromptTemplateUpdateDTO(CamelModel):
    """更新 Prompt 模板；业务编码 code 创建后不可修改。"""

    model_config = ConfigDict(extra="forbid")

    # Optional 在这里表示字段可以不传，不表示数据库字段允许更新成 NULL。
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    system_prompt: str | None = Field(default=None, min_length=1)
    user_prompt: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_short_text(cls, value: Any) -> Any:
        """去掉名称和说明首尾空格。"""

        return value.strip() if isinstance(value, str) else value

    @field_validator("system_prompt", "user_prompt", mode="before")
    @classmethod
    def reject_blank_prompt(cls, value: Any) -> Any:
        """保留 Prompt 排版，同时拒绝全空格内容。"""

        if isinstance(value, str) and not value.strip():
            return ""
        return value

    @model_validator(mode="after")
    def validate_update_fields(self) -> PromptTemplateUpdateDTO:
        """拒绝空更新，以及把数据库必填字段显式更新成 null。"""

        if not self.model_fields_set:
            raise ValueError("至少提供一个需要更新的字段")

        null_fields = [field_name for field_name in self.model_fields_set if getattr(self, field_name) is None]
        if null_fields:
            raise ValueError(f"以下字段不能设置为空：{', '.join(sorted(null_fields))}")
        return self


class PromptTemplatePreviewDTO(CamelModel):
    """预览时提供运行变量；接口只渲染文本，不调用模型。"""

    variables: dict[str, Any] = Field(default_factory=dict)


class PromptTextPreviewDTO(PromptTemplatePreviewDTO):
    """预览尚未保存的编辑内容。"""

    code: str = Field(min_length=1, max_length=80)
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
