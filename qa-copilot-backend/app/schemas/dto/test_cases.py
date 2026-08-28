from typing import Any

from pydantic import Field, field_validator, model_validator

from app.core.constants import (
    CaseReviewAction,
    RequirementCoverageType,
    TestAssetPriority,
    TestCaseType,
)
from app.schemas.camel_model import CamelModel


class TestCaseStepDTO(CamelModel):
    """创建或整体编辑用例时接收的一条结构化步骤。"""

    step_no: int = Field(ge=1)
    action: str = Field(min_length=1, max_length=10000)
    test_data: Any | None = Field(default=None, description="结构化测试数据，可为对象、数组或简单值")
    expected_result: str = Field(min_length=1, max_length=10000)

    @field_validator("action", "expected_result", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class TestCaseCreateDTO(CamelModel):
    """人工创建测试用例；project_id 由接口路径提供。"""

    module_id: int | None = Field(default=None, gt=0)
    case_code: str | None = Field(default=None, min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    case_type: TestCaseType = TestCaseType.FUNCTIONAL
    priority: TestAssetPriority = TestAssetPriority.P2
    preconditions: str = Field(default="", max_length=10000)
    expected_summary: str = Field(default="", max_length=10000)
    automatable: bool = False
    version: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    steps: list[TestCaseStepDTO] = Field(default_factory=list, max_length=200)
    requirement_item_ids: list[int] = Field(default_factory=list, max_length=500)

    @field_validator("case_code", "title", "preconditions", "expected_summary", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class RequirementCaseLinkDTO(CamelModel):
    """人工调整一条需求点与用例之间的覆盖关系。"""

    requirement_item_id: int = Field(gt=0)
    test_case_id: int = Field(gt=0)
    coverage_type: RequirementCoverageType
    confidence: float = Field(default=1.0, ge=0, le=1)
    evidence: dict[str, Any] = Field(default_factory=dict)


class CaseReviewDTO(CamelModel):
    """审核 AI 用例时接收的动作和说明。"""

    action: CaseReviewAction
    comment: str = Field(default="", max_length=2000)

    @field_validator("comment", mode="before")
    @classmethod
    def strip_comment(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class CaseBatchReviewDTO(CaseReviewDTO):
    """批量审核多条测试用例时接收的用例 ID、统一动作和审核说明。

    功能：限制单次最多处理 200 条，并只开放可以安全批量执行的动作。
    作用：API 将它交给与单条审核共用的状态机，避免批量入口绕过业务规则。
    为什么用它：修改和标记重复通常需要每条不同内容，不适合整批套用；接受、
    驳回和发布具有统一语义，可以在一个数据库事务中原子完成。
    """

    test_case_ids: list[int] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_batch_action_and_ids(self):
        """拒绝重复 ID 和不适合批量执行的审核动作。"""
        if len(self.test_case_ids) != len(set(self.test_case_ids)):
            raise ValueError("test_case_ids 不能重复")
        allowed_actions = {
            CaseReviewAction.ACCEPT,
            CaseReviewAction.REJECT,
            CaseReviewAction.PUBLISH,
        }
        if self.action not in allowed_actions:
            raise ValueError("批量审核仅支持接受、驳回和发布")
        return self
