"""定时回归计划返回结构。"""

from datetime import datetime

from app.schemas.camel_model import CamelModel


class AutomationScheduleVO(CamelModel):
    id: int
    project_id: int
    name: str
    definition_id: int
    definition_name: str
    environment_id: int
    environment_name: str
    cron_expression: str
    timezone: str
    timeout_seconds: int
    enabled: bool
    next_run_at: datetime
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
