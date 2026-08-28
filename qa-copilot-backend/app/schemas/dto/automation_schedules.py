"""定时回归计划请求结构。"""

from pydantic import Field

from app.schemas.camel_model import CamelModel


class AutomationScheduleCreateDTO(CamelModel):
    name: str = Field(min_length=1, max_length=160)
    definition_id: int = Field(gt=0)
    environment_id: int = Field(gt=0)
    cron_expression: str = Field(min_length=5, max_length=120)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    timeout_seconds: int = Field(default=300, ge=10, le=7200)
    enabled: bool = True


class AutomationScheduleUpdateDTO(AutomationScheduleCreateDTO):
    """更新采用完整替换，避免前端显示值与实际调度条件不一致。"""
