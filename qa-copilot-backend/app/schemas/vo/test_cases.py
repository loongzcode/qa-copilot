from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.constants import (
    CaseGenerationTaskStatus,
    RequirementCoverageType,
    TestAssetPriority,
    TestCaseSource,
    TestCaseStatus,
    TestCaseType,
)
from app.schemas.camel_model import CamelModel
from pydantic import Field


class TestCaseStepVO(CamelModel):
    """返回给前端的一条测试步骤。"""

    id: int
    test_case_id: int
    step_no: int
    action: str
    test_data: Any | None
    expected_result: str
    created_at: datetime
    updated_at: datetime


class TestCaseVO(CamelModel):
    """测试用例主信息及其有序步骤。"""

    id: int
    project_id: int
    module_id: int | None
    module_name: str | None
    case_code: str | None
    title: str
    case_type: TestCaseType
    priority: TestAssetPriority
    preconditions: str
    expected_summary: str
    status: TestCaseStatus
    source: TestCaseSource
    automatable: bool
    version: int
    metadata: dict[str, Any]
    created_by: int | None
    created_by_name: str | None
    updated_by: int | None
    steps: list[TestCaseStepVO] = Field(default_factory=list)
    requirement_item_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class RequirementCaseLinkVO(CamelModel):
    """覆盖矩阵中的一条关系。"""

    requirement_item_id: int
    test_case_id: int
    coverage_type: RequirementCoverageType
    confidence: Decimal | None
    evidence: dict[str, Any]


class CoverageLinkVO(RequirementCaseLinkVO):
    """覆盖矩阵中带有用例可读信息的一条覆盖关系。"""

    test_case_code: str | None
    test_case_title: str


class CoverageRowVO(CamelModel):
    """一个原子需求点及其当前覆盖结论。"""

    requirement_item: RequirementItemVO
    coverage_status: RequirementCoverageType | str
    links: list[CoverageLinkVO] = Field(default_factory=list)


class CoverageMatrixVO(CamelModel):
    """前端覆盖分析页面需要的完整矩阵和汇总数字。"""

    requirement_id: int
    total_items: int = Field(ge=0)
    full_count: int = Field(ge=0)
    partial_count: int = Field(ge=0)
    uncovered_count: int = Field(ge=0)
    rows: list[CoverageRowVO] = Field(default_factory=list)


class TestCaseRequirementItemOptionVO(CamelModel):
    """测试用例编辑表单中的已确认需求点选项。"""

    id: int
    requirement_id: int
    requirement_title: str
    item_code: str | None
    title: str
    item_type: str
    priority: str


class CaseGenerationTaskVO(CamelModel):
    """向前端展示一次用例生成任务的进度和审计快照。"""

    id: int
    project_id: int
    requirement_id: int
    requirement_title: str | None = None
    model_id: int | None
    prompt_template_id: int | None
    status: CaseGenerationTaskStatus
    input_snapshot: dict[str, Any]
    output_snapshot: dict[str, Any]
    retrieval_snapshot: dict[str, Any]
    progress: int = Field(ge=0, le=100)
    current_stage: str | None
    error_message: str | None
    requested_by: int | None
    started_at: datetime | None
    finished_at: datetime | None
    draft_cases: list[TestCaseVO] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# CoverageRowVO 引用了需求模块中的 VO。放在文件末尾导入可以避免两个 VO 文件
# 在模块加载时互相导入，从而产生循环导入异常。
from app.schemas.vo.requirements import RequirementItemVO  # noqa: E402

CoverageRowVO.model_rebuild()
