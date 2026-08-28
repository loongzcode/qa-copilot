"""测试用例实体到接口 VO 的集中转换函数。"""

from app.core.constants import (
    CaseGenerationTaskStatus,
    TestAssetPriority,
    TestCaseSource,
    TestCaseStatus,
    TestCaseType,
)
from app.models import CaseGenerationTask, TestCase
from app.schemas.vo.test_cases import (
    CaseGenerationTaskVO,
    TestCaseStepVO,
    TestCaseVO,
)


def test_case_to_vo(
    test_case: TestCase,
    requirement_item_ids: list[int] | None = None,
) -> TestCaseVO:
    """把用例主记录、关联信息和有序步骤转换成前端 VO。

    功能：统一枚举转换、关系对象空值处理和步骤排序。
    作用：列表、详情、生成任务和审核接口都复用相同输出格式。
    为什么用它：避免多个 Service 各自复制字段映射；显式排序可以抵消数据库
    预加载时未承诺顺序的问题，让前端始终按 step_no 展示。
    """
    steps = [
        TestCaseStepVO.model_validate(step)
        for step in sorted(test_case.steps, key=lambda item: (item.step_no, item.id))
    ]
    return TestCaseVO(
        id=test_case.id,
        project_id=test_case.project_id,
        module_id=test_case.module_id,
        module_name=test_case.module.name if test_case.module else None,
        case_code=test_case.case_code,
        title=test_case.title,
        case_type=TestCaseType(test_case.case_type),
        priority=TestAssetPriority(test_case.priority),
        preconditions=test_case.preconditions,
        expected_summary=test_case.expected_summary,
        status=TestCaseStatus(test_case.status),
        source=TestCaseSource(test_case.source),
        automatable=test_case.automatable,
        version=test_case.version,
        metadata=test_case.case_metadata,
        created_by=test_case.created_by,
        created_by_name=(
            test_case.creator.display_name if test_case.creator is not None else None
        ),
        updated_by=test_case.updated_by,
        steps=steps,
        requirement_item_ids=requirement_item_ids or [],
        created_at=test_case.created_at,
        updated_at=test_case.updated_at,
    )


def generation_task_to_vo(
    task: CaseGenerationTask,
    draft_cases: list[TestCaseVO] | None = None,
) -> CaseGenerationTaskVO:
    """把生成任务及其草稿用例转换成轮询和审核页面使用的 VO。"""
    return CaseGenerationTaskVO(
        id=task.id,
        project_id=task.project_id,
        requirement_id=task.requirement_id,
        requirement_title=(
            task.requirement.title if task.requirement is not None else None
        ),
        model_id=task.model_id,
        prompt_template_id=task.prompt_template_id,
        status=CaseGenerationTaskStatus(task.status),
        input_snapshot=task.input_snapshot,
        output_snapshot=task.output_snapshot,
        retrieval_snapshot=task.retrieval_snapshot,
        progress=task.progress,
        current_stage=task.current_stage,
        error_message=task.error_message,
        requested_by=task.requested_by,
        started_at=task.started_at,
        finished_at=task.finished_at,
        draft_cases=draft_cases or [],
        created_at=task.created_at,
        updated_at=task.updated_at,
    )
