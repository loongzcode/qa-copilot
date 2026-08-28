from datetime import datetime

from app.core.constants import AIProviderType
from app.schemas.camel_model import CamelModel


class AIProviderVO(CamelModel):
    """AI 服务商管理接口返回的数据，密钥只返回脱敏内容。"""

    id: int
    name: str
    provider_type: AIProviderType
    base_url: str | None
    api_key_masked: str = ""
    custom_headers: dict[str, str]
    timeout_seconds: int
    max_retries: int
    enabled: bool
    created_at: datetime
    updated_at: datetime
