from pydantic import Field

from app.core.constants import AIProviderType
from app.schemas.camel_model import CamelModel


class AIProviderBaseDTO(CamelModel):
    """创建 AI 服务商时使用的公共配置。"""

    name: str = Field(min_length=1, max_length=100)
    provider_type: AIProviderType = AIProviderType.OPENAI_RESPONSES
    base_url: str | None = Field(default=None, max_length=500)
    custom_headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=120, ge=5, le=600)
    max_retries: int = Field(default=2, ge=0, le=10)
    enabled: bool = True


class AIProviderCreateDTO(AIProviderBaseDTO):
    """创建 AI 服务商参数。"""

    api_key: str = Field(default="", max_length=500)


class AIProviderUpdateDTO(CamelModel):
    """编辑 AI 服务商参数。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    provider_type: AIProviderType | None = None
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    custom_headers: dict[str, str] | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)
    max_retries: int | None = Field(default=None, ge=0, le=10)
    enabled: bool | None = None
