"""覆盖分析与缺失用例生成使用的结构化模型输出契约。"""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.constants import RequirementCoverageType, TestAssetPriority, TestCaseType


class CoverageDecision(BaseModel):
    """模型对一个需求点与一条历史用例作出的覆盖判断。"""

    model_config = ConfigDict(extra="forbid")

    requirement_item_id: int = Field(gt=0)
    test_case_id: int = Field(gt=0)
    coverage_type: RequirementCoverageType
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=2000)
    covered_aspects: list[str] = Field(default_factory=list, max_length=50)
    missing_aspects: list[str] = Field(default_factory=list, max_length=50)


class CoverageAnalysisOutput(BaseModel):
    """一次覆盖分析允许写入数据库的全部结构化结论。"""

    model_config = ConfigDict(extra="forbid")

    decisions: list[CoverageDecision] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def reject_duplicate_pairs(self) -> Self:
        """同一需求点和用例只能有一条覆盖结论。"""
        pairs = [
            (item.requirement_item_id, item.test_case_id)
            for item in self.decisions
        ]
        if len(pairs) != len(set(pairs)):
            raise ValueError("覆盖分析包含重复的需求点与用例组合")
        return self


class GeneratedCaseStep(BaseModel):
    """AI 生成用例中的一条结构化步骤。"""

    model_config = ConfigDict(extra="forbid")

    step_no: int = Field(ge=1)
    action: str = Field(min_length=1, max_length=10000)
    test_data: Any | None = None
    expected_result: str = Field(min_length=1, max_length=10000)

    @field_validator("action", "expected_result", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class GeneratedTestCase(BaseModel):
    """模型生成但尚未落库的一条测试用例草稿。"""

    model_config = ConfigDict(extra="forbid")

    local_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    case_type: TestCaseType = TestCaseType.FUNCTIONAL
    priority: TestAssetPriority = TestAssetPriority.P2
    preconditions: str = Field(default="", max_length=10000)
    expected_summary: str = Field(default="", max_length=10000)
    automatable: bool = False
    requirement_item_ids: list[int] = Field(min_length=1, max_length=100)
    generation_reason: str = Field(min_length=1, max_length=2000)
    source_case_ids: list[int] = Field(default_factory=list, max_length=100)
    source_knowledge_chunk_ids: list[int] = Field(default_factory=list, max_length=100)
    confidence: float = Field(ge=0, le=1)
    tags: list[str] = Field(default_factory=list, max_length=50)
    steps: list[GeneratedCaseStep] = Field(min_length=1, max_length=200)

    @field_validator("title", "preconditions", "expected_summary", "generation_reason", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_steps_and_links(self) -> Self:
        """确保步骤连续、需求点不重复，避免把不稳定结构写入数据库。"""
        expected_step_numbers = list(range(1, len(self.steps) + 1))
        actual_step_numbers = [step.step_no for step in self.steps]
        if actual_step_numbers != expected_step_numbers:
            raise ValueError("测试步骤 step_no 必须从 1 开始连续递增")
        if len(self.requirement_item_ids) != len(set(self.requirement_item_ids)):
            raise ValueError("requirement_item_ids 不能重复")
        if len(self.source_knowledge_chunk_ids) != len(
            set(self.source_knowledge_chunk_ids)
        ):
            raise ValueError("source_knowledge_chunk_ids 不能重复")
        # 当前自动化执行器只支持接口请求。模型把功能/UI/其他用例误标为可自动化时，
        # 在草稿落库前纠正为 False，避免审核人员发布后才发现无法进入自动化模块。
        if self.case_type != TestCaseType.API:
            self.automatable = False
        return self


class CaseGenerationOutput(BaseModel):
    """缺失用例生成 Graph 最终允许落库的输出。"""

    model_config = ConfigDict(extra="forbid")

    cases: list[GeneratedTestCase] = Field(default_factory=list, max_length=200)
    warnings: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def reject_duplicate_local_ids(self) -> Self:
        local_ids = [item.local_id for item in self.cases]
        if len(local_ids) != len(set(local_ids)):
            raise ValueError("生成用例 local_id 不能重复")
        return self
