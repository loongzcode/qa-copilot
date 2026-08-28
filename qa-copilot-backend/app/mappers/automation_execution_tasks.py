from app.core.constants import AutomationExecutionStatus, AutomationStepStatus
from app.models import AutomationExecutionStepResult, AutomationExecutionTask
from app.schemas.vo.automation_execution_tasks import (
    AutomationExecutionReportVO,
    AutomationExecutionStepResultVO,
    AutomationExecutionTaskVO,
)


def automation_execution_task_to_vo(entity: AutomationExecutionTask) -> AutomationExecutionTaskVO:
    """把任务实体及其预加载关系转换为前端安全视图。"""
    return AutomationExecutionTaskVO(
        id=entity.id,
        project_id=entity.project_id,
        definition_id=entity.definition_id,
        definition_name=entity.definition.name,
        definition_version=entity.definition.version,
        environment_id=entity.environment_id,
        environment_name=entity.environment.name,
        status=AutomationExecutionStatus(entity.status),
        progress=entity.progress,
        current_stage=entity.current_stage,
        timeout_seconds=entity.timeout_seconds,
        celery_task_id=entity.celery_task_id,
        result_summary=entity.result_summary,
        error_message=entity.error_message,
        requested_by=entity.requested_by,
        requested_by_name=entity.requester.display_name if entity.requester else None,
        started_at=entity.started_at,
        finished_at=entity.finished_at,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def automation_execution_report_to_vo(
    task: AutomationExecutionTask,
    steps: list[AutomationExecutionStepResult],
) -> AutomationExecutionReportVO:
    """组合任务汇总和逐步骤结果，数据库实体不会直接暴露给 API。"""
    return AutomationExecutionReportVO(
        task=automation_execution_task_to_vo(task),
        steps=[
            AutomationExecutionStepResultVO(
                id=step.id,
                step_no=step.step_no,
                name=step.name,
                status=AutomationStepStatus(step.status),
                method=step.method,
                path=step.path,
                status_code=step.status_code,
                duration_ms=step.duration_ms,
                request_summary=step.request_summary,
                response_summary=step.response_summary,
                assertions=step.assertions,
                error_message=step.error_message,
            )
            for step in steps
        ],
    )
