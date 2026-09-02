"""Supervisor Agent 接收目标和结构化计划所使用的数据对象。"""

from typing import Any

from pydantic import Field

from app.core.constants import SupervisorApprovalDecision
from app.schemas.camel_model import CamelModel


class SupervisorPlanStepDTO(CamelModel):
    """Supervisor 计划中的一个受控步骤。

    功能：描述“调用哪个已登记能力、为什么调用、传什么参数以及依赖哪些前置步骤”。
    作用：作为模型规划结果与确定性安全校验器之间的稳定数据契约。
    为什么用它：不能直接执行模型生成的自由文本；Pydantic 会先限制字段类型和长度，
    后续校验器再检查工具白名单、权限和人工审批条件。
    """

    step_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    capability_code: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=20)


class SupervisorPlanDTO(CamelModel):
    """Supervisor 为一个用户目标生成的完整候选计划。

    功能：保存目标和按执行顺序排列的步骤。
    作用：模型只能提出这份候选计划，不能凭借它直接修改数据库或外部系统。
    为什么用它：把“模型负责规划”和“程序负责授权执行”分开，既保留 Agent 的灵活性，
    又避免模型绕过权限、人工作业关卡或工具审批流程。
    """

    goal: str = Field(min_length=1, max_length=2000)
    steps: list[SupervisorPlanStepDTO] = Field(min_length=1, max_length=20)


class SupervisorCreateRunDTO(CamelModel):
    """用户提交给 Supervisor 的开放目标和可选业务上下文。

    功能：接收目标正文以及需求、知识库等业务对象的 ID 上下文。
    作用：后续 API 只需要传入该 DTO，Service 会补充项目、用户和权限快照。
    为什么用它：上下文与目标分开后，模型无需从自然语言猜测所有业务 ID；使用字典保留扩展性，
    Service 仍会限制大小并拒绝密码、Token 等敏感键，不能把它当成任意配置容器。
    """

    goal: str = Field(min_length=1, max_length=2000)
    business_context: dict[str, Any] = Field(default_factory=dict)
    session_id: int | None = Field(default=None, gt=0)


class SupervisorCreateSessionDTO(CamelModel):
    """创建聊天会话；标题为空时由第一条目标自动生成。"""

    title: str = Field(default="新会话", min_length=1, max_length=120)


class SupervisorApprovalDTO(CamelModel):
    """人工审批一个等待中的 Supervisor 步骤。"""

    decision: SupervisorApprovalDecision
    comment: str = Field(default="", max_length=2000)
