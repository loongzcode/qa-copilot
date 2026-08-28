from datetime import datetime
from typing import Any

from app.core.constants import (
    KnowledgeDocumentParseStatus,
    RequirementExtractionStage,
    RequirementExtractionTaskStatus,
    RequirementItemType,
    RequirementStatus,
    TestAssetPriority,
)
from app.schemas.camel_model import CamelModel
from pydantic import Field


class RequirementItemVO(CamelModel):
    """返回给前端的一条可编辑原子需求点。"""

    id: int
    requirement_id: int
    parent_id: int | None
    item_code: str | None
    title: str
    description: str
    item_type: RequirementItemType
    priority: TestAssetPriority
    acceptance_criteria: str
    source_locator: dict[str, Any]
    ai_generated: bool
    confirmed: bool
    order_no: int
    created_at: datetime
    updated_at: datetime


class RequirementVO(CamelModel):
    """需求列表和详情共用的基础返回结构。"""

    id: int
    project_id: int
    module_id: int | None
    module_name: str | None
    document_id: int | None
    document_title: str | None
    document_parse_status: KnowledgeDocumentParseStatus | None
    title: str
    version: str
    status: RequirementStatus
    source_url: str | None
    summary: str
    metadata: dict[str, Any]
    created_by: int | None
    created_by_name: str | None
    item_count: int = Field(default=0, ge=0)
    confirmed_item_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime


class RequirementDetailVO(RequirementVO):
    """需求详情在基础信息之外携带完整需求点列表。"""

    items: list[RequirementItemVO] = Field(default_factory=list)


class RequirementModuleOptionVO(CamelModel):
    """新建或编辑需求时，模块下拉框中的一个选项。"""

    id: int
    name: str


class RequirementDocumentOptionVO(CamelModel):
    """新建或编辑需求时，已有需求来源文档下拉框中的一个选项。"""

    id: int
    title: str
    version: int


class RequirementKnowledgeBaseOptionVO(CamelModel):
    """直接上传需求来源文档时，用于选择保存位置的知识库选项。"""

    id: int
    name: str


class RequirementFormOptionsVO(CamelModel):
    """需求表单一次加载所需的模块、知识库和已有来源文档选项。"""

    modules: list[RequirementModuleOptionVO] = Field(default_factory=list)
    knowledge_bases: list[RequirementKnowledgeBaseOptionVO] = Field(
        default_factory=list
    )
    documents: list[RequirementDocumentOptionVO] = Field(default_factory=list)


class RequirementExtractionTaskVO(CamelModel):
    """返回给前端的一次需求拆解任务状态和审计信息。"""

    id: int
    project_id: int
    requirement_id: int
    celery_task_id: str
    model_id: int | None
    prompt_template_id: int | None
    status: RequirementExtractionTaskStatus
    progress: int = Field(ge=0, le=100)
    current_stage: RequirementExtractionStage
    input_snapshot: dict[str, Any]
    output_snapshot: dict[str, Any]
    error_message: str | None
    requested_by: int | None
    requested_by_name: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
