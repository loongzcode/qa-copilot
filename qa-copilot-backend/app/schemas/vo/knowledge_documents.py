from datetime import datetime
from typing import Any

from app.core.constants import (
    KnowledgeDocumentParseStatus,
    KnowledgeDocumentSourceType,
    KnowledgeDocumentType,
)
from app.schemas.camel_model import CamelModel


class KnowledgeDocumentVO(CamelModel):
    """文档列表和详情接口返回给前端的数据。"""

    id: int
    knowledge_base_id: int
    module_id: int | None
    module_name: str | None
    document_type: KnowledgeDocumentType
    title: str
    source_type: KnowledgeDocumentSourceType
    source_url: str | None
    original_filename: str | None
    mime_type: str | None
    size_bytes: int | None
    sha256: str | None
    version: int
    parse_status: KnowledgeDocumentParseStatus
    error_message: str | None
    index_task_id: str | None
    index_queued_at: datetime | None
    index_started_at: datetime | None
    index_heartbeat_at: datetime | None
    index_completed_at: datetime | None
    index_recovery_count: int
    metadata: dict[str, Any]
    chunk_count: int
    created_by: int | None
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime
