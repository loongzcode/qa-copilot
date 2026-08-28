from pydantic import Field

from app.core.config import settings
from app.schemas.camel_model import CamelModel


class AutomationExecutionCreateDTO(CamelModel):
    """提交自动化执行任务时选择定义、环境和整次任务超时。"""

    definition_id: int = Field(gt=0)
    environment_id: int = Field(gt=0)
    timeout_seconds: int = Field(
        default_factory=lambda: settings.automation_execution_default_timeout_seconds,
        ge=10,
        le=settings.automation_execution_max_timeout_seconds,
    )
