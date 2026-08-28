from datetime import datetime

from app.schemas.camel_model import CamelModel


class AIModelVO(CamelModel):
    """AI 模型管理接口返回的数据。"""

    id: int
    provider_id: int
    name: str
    model_id: str
    reasoning_effort: str | None
    max_output_tokens: int
    enabled: bool
    is_default: bool
    task_types: list[str]
    provider_name: str = ""
    created_at: datetime
    updated_at: datetime
    context_window_tokens: int


class AIConnectionResultVO(CamelModel):
    """AI 模型连接测试结果。"""

    success: bool
    content: str
    latency_ms: int
