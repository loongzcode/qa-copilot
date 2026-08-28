"""约束 Supervisor 规划模型返回的 JSON 结构。"""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SupervisorPlannedStep(BaseModel):
    """模型提出的一个候选步骤，尚未获得任何执行权限。

    功能：限制步骤编号、能力编码、用途、参数和依赖的结构。
    作用：模型原始文本必须先转换成该对象，之后才能进入能力白名单校验。
    为什么用它：``extra='forbid'`` 会拒绝模型临时发明的字段；字段上限可以防止异常响应
    写入过大的参数或依赖列表。它只描述计划，不保存权限和风险，二者必须从服务端能力目录取得。
    """

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    capability_code: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("step_id", "capability_code", "purpose", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        """清理文本两侧空格，让纯空格值继续由 Field 的最小长度拒绝。"""
        return value.strip() if isinstance(value, str) else value


class SupervisorPlanningOutput(BaseModel):
    """一次 Supervisor 模型规划返回的全部候选步骤。

    功能：保证至少一个、最多二十个步骤，并拒绝重复步骤编号。
    作用：通过结构校验后再转换成 SupervisorPlanDTO，进入权限和来源校验。
    为什么用它：步骤数量上限限制模型成本和失控循环；跨步骤唯一性必须看到完整列表，
    所以使用 model_validator，而不是在单个步骤中判断。
    """

    model_config = ConfigDict(extra="forbid")

    steps: list[SupervisorPlannedStep] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> Self:
        """拒绝重复步骤编号，避免依赖解析到不确定目标。"""
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Supervisor 计划步骤编号不能重复")
        return self
