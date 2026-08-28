"""需求管理实体到接口 VO 的转换函数。

需求主记录 Service 和需求点 Service 都需要返回相同的 VO。把转换集中在这里，
可以避免两个 Service 各复制一套字段映射，后续 VO 增加字段时只修改一个位置。
"""

from app.core.constants import RequirementStatus
from app.models import Requirement, RequirementExtractionTask, RequirementItem
from app.schemas.vo.requirements import (
    RequirementDetailVO,
    RequirementExtractionTaskVO,
    RequirementItemVO,
    RequirementVO,
)


def requirement_item_to_vo(item: RequirementItem) -> RequirementItemVO:
    """把一条需求点 ORM 实体转换成前端需要的 VO。"""

    return RequirementItemVO.model_validate(item)


def requirement_to_vo(requirement: Requirement) -> RequirementVO:
    """转换需求主记录，并安全读取查询时预加载的关联对象。"""

    return RequirementVO(
        id=requirement.id,
        project_id=requirement.project_id,
        module_id=requirement.module_id,
        module_name=requirement.module.name if requirement.module else None,
        document_id=requirement.document_id,
        document_title=requirement.document.title if requirement.document else None,
        document_parse_status=(
            requirement.document.parse_status if requirement.document else None
        ),
        title=requirement.title,
        version=requirement.version,
        status=RequirementStatus(requirement.status),
        source_url=requirement.source_url,
        summary=requirement.summary,
        metadata=requirement.requirement_metadata,
        created_by=requirement.created_by,
        created_by_name=requirement.creator.display_name if requirement.creator else None,
        item_count=requirement.item_count,
        confirmed_item_count=requirement.confirmed_item_count,
        created_at=requirement.created_at,
        updated_at=requirement.updated_at,
    )


def requirement_detail_to_vo(requirement: Requirement) -> RequirementDetailVO:
    """在需求主记录 VO 上补充已经按顺序加载的需求点列表。"""

    base_vo = requirement_to_vo(requirement)
    return RequirementDetailVO(
        **base_vo.model_dump(),
        items=[requirement_item_to_vo(item) for item in requirement.items],
    )


def requirement_extraction_task_to_vo(
    task: RequirementExtractionTask,
) -> RequirementExtractionTaskVO:
    """把任务实体转换为前端轮询进度时使用的 VO。"""

    return RequirementExtractionTaskVO(
        id=task.id,
        project_id=task.project_id,
        requirement_id=task.requirement_id,
        celery_task_id=task.celery_task_id,
        model_id=task.model_id,
        prompt_template_id=task.prompt_template_id,
        status=task.status,
        progress=task.progress,
        current_stage=task.current_stage,
        input_snapshot=task.input_snapshot,
        output_snapshot=task.output_snapshot,
        error_message=task.error_message,
        requested_by=task.requested_by,
        requested_by_name=(
            task.requester.display_name if task.requester is not None else None
        ),
        started_at=task.started_at,
        finished_at=task.finished_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )
