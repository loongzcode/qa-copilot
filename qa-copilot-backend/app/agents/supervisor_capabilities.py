"""Supervisor Agent 与 MCP 共用的受控能力目录。"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import ProjectStatus, TestCaseSource, TestCaseStatus, ToolRisk
from app.core.permissions import Permission


class QualityDeliveryStatusArguments(BaseModel):
    """查询质量交付状态能力允许接收的全部参数。"""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(gt=0)
    requirement_id: int = Field(gt=0)


class GenerateMissingCasesArguments(BaseModel):
    """生成缺失测试用例能力允许接收的项目和需求编号。"""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(gt=0)
    requirement_id: int = Field(gt=0)


class ProjectListArguments(BaseModel):
    """分页查询当前用户可访问项目所需参数。"""

    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(default="", max_length=160)
    status: ProjectStatus | None = None
    current: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class RequirementDetailArguments(BaseModel):
    """查询项目内一条需求详情所需参数。"""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(gt=0)
    requirement_id: int = Field(gt=0)


class TestCaseListArguments(BaseModel):
    """分页查询项目测试用例所需参数。"""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(gt=0)
    keyword: str = Field(default="", max_length=200)
    module_id: int | None = Field(default=None, gt=0)
    status: TestCaseStatus | None = None
    source: TestCaseSource | None = None
    current: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


@dataclass(frozen=True, slots=True)
class AgentCapabilityDefinition:
    """描述一个可以被 Agent 规划、但仍由业务代码控制的能力。

    功能：集中记录能力编码、风险、权限、是否只读以及允许从哪些入口调用。
    作用：Supervisor 计划校验和 Model Context Protocol（模型上下文协议）工具暴露
    共用同一份白名单，避免两个入口产生不同的安全规则。
    为什么用它：能力元数据是静态配置，冻结的数据类轻量、可读且不允许运行时被意外修改；
    真正执行仍由 Service 完成，这里不保存可绕过业务层的函数引用。
    """

    code: str
    name: str
    description: str
    risk_level: ToolRisk
    required_permission: str
    read_only: bool
    supervisor_enabled: bool
    mcp_enabled: bool
    requires_human_approval: bool
    service_operation: str
    arguments_model: type[BaseModel] | None = None


class AgentCapabilityRegistry:
    """维护进程内不可重复的 Agent 能力白名单。

    功能：注册、查询并筛选 Supervisor/MCP 可以看到的能力。
    作用：所有模型计划都必须先在这里找到能力定义，未知编码不会进入执行器。
    为什么用它：显式注册比动态扫描模块更容易审计，也不会因为新建了一个函数就意外暴露给模型；
    替代方案是使用插件自动发现，但企业权限边界下显式白名单更安全。
    """

    def __init__(self, definitions: tuple[AgentCapabilityDefinition, ...] = ()) -> None:
        self._definitions: dict[str, AgentCapabilityDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: AgentCapabilityDefinition) -> None:
        """注册并检查一项能力。

        功能：拒绝重复编码和不安全的 MCP 直接暴露配置。
        作用：在应用启动或测试构建目录时尽早发现配置错误。
        为什么用它：MCP 第一阶段只开放只读能力；写操作必须先接入现有预览、审批和审计流程，
        不能仅靠模型参数声明为安全。
        """
        if definition.code in self._definitions:
            raise ValueError(f"Agent 能力编码重复：{definition.code}")
        if definition.mcp_enabled and not definition.read_only:
            raise ValueError(f"MCP 第一阶段禁止直接暴露写能力：{definition.code}")
        if definition.risk_level in {ToolRisk.MEDIUM, ToolRisk.HIGH} and not definition.requires_human_approval:
            raise ValueError(f"中高风险能力必须要求人工审批：{definition.code}")
        self._definitions[definition.code] = definition

    def get(self, code: str) -> AgentCapabilityDefinition | None:
        """按稳定编码读取能力；未知能力返回 None 交给计划校验器形成可读错误。"""
        return self._definitions.get(code)

    def list_for_supervisor(self) -> tuple[AgentCapabilityDefinition, ...]:
        """返回允许 Supervisor 规划的能力，供后续生成模型工具说明。"""
        return tuple(item for item in self._definitions.values() if item.supervisor_enabled)

    def list_for_mcp(self) -> tuple[AgentCapabilityDefinition, ...]:
        """返回允许 MCP 客户端发现的只读能力，不包含内部能力和审批型写能力。"""
        return tuple(item for item in self._definitions.values() if item.mcp_enabled)


SUPERVISOR_CAPABILITY_REGISTRY = AgentCapabilityRegistry(
    (
        AgentCapabilityDefinition(
            code="quality_delivery.get_status",
            name="查询质量交付状态",
            description="查询指定需求当前处于需求拆解、人工确认、用例生成或自动化准备的哪个阶段。",
            risk_level=ToolRisk.LOW,
            required_permission=Permission.REQUIREMENT_VIEW,
            read_only=True,
            supervisor_enabled=True,
            mcp_enabled=True,
            requires_human_approval=False,
            service_operation="QualityDeliveryService.get_status",
            arguments_model=QualityDeliveryStatusArguments,
        ),
        AgentCapabilityDefinition(
            code="project.list_accessible",
            name="查询可访问项目",
            description="分页查询当前登录用户有权访问的测试项目，不返回任何密钥或环境变量。",
            risk_level=ToolRisk.LOW,
            required_permission=Permission.PROJECT_INFO_VIEW,
            read_only=True,
            supervisor_enabled=False,
            mcp_enabled=True,
            requires_human_approval=False,
            service_operation="TestProjectsService.list_projects",
            arguments_model=ProjectListArguments,
        ),
        AgentCapabilityDefinition(
            code="requirement.get_detail",
            name="查询需求详情",
            description="查询项目内一条需求及其结构化需求点，仍受项目成员权限限制。",
            risk_level=ToolRisk.LOW,
            required_permission=Permission.REQUIREMENT_VIEW,
            read_only=True,
            supervisor_enabled=False,
            mcp_enabled=True,
            requires_human_approval=False,
            service_operation="RequirementsService.get_requirement_detail",
            arguments_model=RequirementDetailArguments,
        ),
        AgentCapabilityDefinition(
            code="test_case.list",
            name="查询测试用例",
            description="分页查询项目内的测试用例、步骤摘要和需求点关联。",
            risk_level=ToolRisk.LOW,
            required_permission=Permission.TEST_CASE_VIEW,
            read_only=True,
            supervisor_enabled=False,
            mcp_enabled=True,
            requires_human_approval=False,
            service_operation="TestCasesService.list_test_cases",
            arguments_model=TestCaseListArguments,
        ),
        AgentCapabilityDefinition(
            code="test_case.generate_missing",
            name="生成缺失测试用例",
            description="针对已确认需求的覆盖缺口创建异步用例生成任务；属于写操作，必须由另一名有权用户审批。",
            risk_level=ToolRisk.MEDIUM,
            required_permission=Permission.TEST_CASE_GENERATE,
            read_only=False,
            supervisor_enabled=True,
            mcp_enabled=False,
            requires_human_approval=True,
            service_operation="TestCasesService.submit_generation",
            arguments_model=GenerateMissingCasesArguments,
        ),
    )
)
