from datetime import datetime

from app.core.constants import TestEnvironmentType
from app.schemas.camel_model import CamelModel
from pydantic import Field


class TestEnvironmentVariableVO(CamelModel):
    """返回给前端的环境变量；敏感值只能返回掩码。"""

    key: str
    value: str
    secret: bool


class TestEnvironmentVO(CamelModel):
    """返回给前端的测试环境。"""

    id: int
    project_id: int
    name: str
    environment_type: TestEnvironmentType
    base_url: str
    allowed_hosts: list[str] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)
    variables: list[TestEnvironmentVariableVO] = Field(default_factory=list)
    variable_count: int = Field(default=0, ge=0)
    enabled: bool
    created_by: int | None
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


class TestEnvironmentConnectionResultVO(CamelModel):
    """测试环境连接结果，不返回请求头或环境变量等敏感内容。"""

    success: bool
    status_code: int | None = None
    latency_ms: int = Field(ge=0)
    message: str
