from datetime import datetime
from typing import Any

from app.core.constants import AutomationDefinitionChangeAction, AutomationDefinitionStatus
from app.schemas.camel_model import CamelModel
from app.schemas.dto.automation_definitions import AutomationDefinitionSpecDTO


class AutomationDefinitionVO(CamelModel):
    """返回给前端的自动化定义、来源版本和审批审计信息。"""

    id: int
    project_id: int
    test_case_id: int
    test_case_title: str
    name: str
    version: int
    status: AutomationDefinitionStatus
    schema_version: str
    source_case_version: int
    definition: AutomationDefinitionSpecDTO
    definition_hash: str
    created_by: int | None
    created_by_name: str | None
    approved_by: int | None
    approved_by_name: str | None
    approved_at: datetime | None
    retired_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AutomationDefinitionChangeVO(CamelModel):
    """一条自动化定义变更快照，供历史时间线和差异查看使用。"""

    id: int
    definition_id: int
    version: int
    action: AutomationDefinitionChangeAction
    before_snapshot: dict[str, Any] | None
    after_snapshot: dict[str, Any] | None
    changed_by: int | None
    changed_by_name: str | None
    created_at: datetime
