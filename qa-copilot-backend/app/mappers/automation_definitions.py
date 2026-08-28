from app.core.constants import AutomationDefinitionStatus
from app.models import AutomationDefinition
from app.schemas.dto.automation_definitions import AutomationDefinitionSpecDTO
from app.schemas.vo.automation_definitions import AutomationDefinitionVO


def automation_definition_to_vo(entity: AutomationDefinition) -> AutomationDefinitionVO:
    """把数据库实体转换成接口对象，并再次验证数据库中的 JSON 符合当前协议。"""
    return AutomationDefinitionVO(
        id=entity.id,
        project_id=entity.project_id,
        test_case_id=entity.test_case_id,
        test_case_title=entity.test_case.title,
        name=entity.name,
        version=entity.version,
        status=AutomationDefinitionStatus(entity.status),
        schema_version=entity.schema_version,
        source_case_version=entity.source_case_version,
        definition=AutomationDefinitionSpecDTO.model_validate(entity.definition),
        definition_hash=entity.definition_hash,
        created_by=entity.created_by,
        created_by_name=entity.creator.display_name if entity.creator else None,
        approved_by=entity.approved_by,
        approved_by_name=entity.approver.display_name if entity.approver else None,
        approved_at=entity.approved_at,
        retired_at=entity.retired_at,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )
