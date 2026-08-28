from pydantic import Field

from app.schemas.camel_model import CamelModel


class AIModelBaseDTO(CamelModel):
    """创建 AI 模型时使用的公共配置。"""

    provider_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=160)
    reasoning_effort: str | None = None
    max_output_tokens: int = Field(default=4096, ge=128, le=128000)
    enabled: bool = True
    is_default: bool = False
    task_types: list[str] = Field(default_factory=list)
    context_window_tokens: int = Field(default=32768, ge=1024, le=2_000_000)


class AIModelCreateDTO(AIModelBaseDTO):
    """创建 AI 模型参数。"""


class AIModelUpdateDTO(CamelModel):
    """编辑 AI 模型参数。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    model_id: str | None = Field(default=None, min_length=1, max_length=160)
    reasoning_effort: str | None = None
    max_output_tokens: int | None = Field(default=None, ge=128, le=128000)
    enabled: bool | None = None
    is_default: bool | None = None
    task_types: list[str] | None = None
    context_window_tokens: int | None = Field(default=None, ge=1024, le=2_000_000)


class AIConnectionTestDTO(CamelModel):
    """测试 AI 模型连接时接收的参数。"""

    model_id: int = Field(gt=0)
    prompt: str = "请回复：连接成功"
