"""Supervisor 目标规划、确定性校验和计划持久化服务。"""

from __future__ import annotations

import json
from collections.abc import Collection
from typing import Any

from app.agents.supervisor_capabilities import SUPERVISOR_CAPABILITY_REGISTRY, AgentCapabilityRegistry
from app.agents.supervisor_planning_graph import (
    SUPERVISOR_PLANNING_GRAPH,
    SupervisorPlanningContext,
)
from app.core.constants import (
    AIModelTaskType,
    CapabilityInvocationSource,
    OutboxAggregateType,
    OutboxEventType,
    ProjectMemberRole,
    SupervisorApprovalDecision,
    SupervisorExecutionStepStatus,
    SupervisorRunStatus,
    SupervisorStepDecision,
    ToolRisk,
)
from app.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    InternalServerException,
    NotFoundException,
)
from app.exceptions.errors import describe_exception
from app.models import AIModel, PromptTemplate, SupervisorPlanStep, SupervisorRun, User
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.repositories.supervisor_repository import SupervisorRepository
from app.repositories.test_project_members_repository import TestProjectMembersRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.schemas.dto.supervisor import (
    SupervisorApprovalDTO,
    SupervisorCreateRunDTO,
    SupervisorPlanDTO,
)
from app.schemas.vo.supervisor import (
    SupervisorPlanStepVO,
    SupervisorPlanValidationVO,
    SupervisorRunDetailVO,
    SupervisorRunVO,
)

_SENSITIVE_CONTEXT_KEYS = {
    "password",
    "passwd",
    "token",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
}
_MAX_BUSINESS_CONTEXT_CHARS = 20_000


class SupervisorService:
    """把用户目标转换成可审计、尚未执行的 Supervisor 计划。

    功能：校验项目、读取模型配置、创建运行记录、调用 LangGraph、保存步骤和最终规划状态。
    作用：它是未来 Supervisor API 的业务入口，也是模型规划与后续执行器之间的事务边界。
    为什么用它：LangGraph 只负责无副作用的规划和校验，数据库提交集中在 Service；
    这样模型重试不会重复插入步骤，任何异常也能把已创建的运行收口为 FAILED。
    """

    def __init__(
        self,
        repository: SupervisorRepository,
        project_repository: TestProjectsRepository,
        project_member_repository: TestProjectMembersRepository,
        ai_model_repository: AIModelRepository,
        prompt_template_repository: PromptTemplateRepository,
        outbox_repository: OutboxEventRepository | None,
        *,
        registry: AgentCapabilityRegistry = SUPERVISOR_CAPABILITY_REGISTRY,
        planning_graph: Any = SUPERVISOR_PLANNING_GRAPH,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.project_member_repository = project_member_repository
        self.ai_model_repository = ai_model_repository
        self.prompt_template_repository = prompt_template_repository
        self.outbox_repository = outbox_repository
        self.registry = registry
        self.planning_graph = planning_graph

    @staticmethod
    def _run_read(run: SupervisorRun) -> SupervisorRunVO:
        """把运行实体转换为列表 VO，不加载和返回步骤快照。"""
        return SupervisorRunVO.model_validate(run)

    @staticmethod
    def _run_detail_read(run: SupervisorRun) -> SupervisorRunDetailVO:
        """把已预加载步骤的运行实体转换成完整详情 VO。

        功能：按数据库 step_no 顺序转换步骤、上下文和结果快照。
        作用：创建、详情和取消接口共用完全一致的响应结构。
        为什么用它：VO 隔离 ORM 实体，避免关系对象或未来新增的内部字段被 FastAPI 自动序列化到前端。
        """
        return SupervisorRunDetailVO(
            **SupervisorRunVO.model_validate(run).model_dump(),
            permission_snapshot=list(run.permission_snapshot),
            context_snapshot=dict(run.context_snapshot),
            result_summary=dict(run.result_summary),
            steps=[SupervisorPlanStepVO.model_validate(step) for step in run.steps],
        )

    @staticmethod
    def _ensure_context_safe(value: Any, path: str = "businessContext") -> None:
        """递归拒绝业务上下文中的明文凭据。

        功能：检查字典和列表中的敏感键，发现非空密码、Token 或密钥时拒绝请求。
        作用：保护 Prompt、Supervisor 运行快照和 AI 调用链路，避免凭据扩散。
        为什么用它：简单脱敏后模型仍可能依赖被遮盖值并生成错误计划；直接拒绝并要求改传连接 ID
        更明确、更安全。替代方案是字段级加密，但模型规划本身不应需要秘密正文。
        """
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in _SENSITIVE_CONTEXT_KEYS and item not in (None, ""):
                    raise BadRequestException(f"{path}.{key} 不允许包含明文凭据，请改传受控连接 ID")
                SupervisorService._ensure_context_safe(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                SupervisorService._ensure_context_safe(item, f"{path}[{index}]")

    async def _load_ai_configuration(self) -> tuple[AIModel, PromptTemplate]:
        """读取并校验 Supervisor 规划使用的默认模型和内置 Prompt。

        功能：检查模型、服务商、任务能力和 ``supervisor_planning`` Prompt 是否启用。
        作用：在创建运行记录前发现配置问题，避免数据库留下无法执行的 PLANNING 记录。
        为什么用它：固定业务编码保证 Prompt 变量契约稳定，数据库配置又允许管理员切换具体模型；
        与硬编码模型相比更适合多服务商环境。
        """
        model = await self.ai_model_repository.get_default_model()
        if model is None or not model.enabled:
            raise InternalServerException("未配置已启用的默认 Supervisor 规划模型")
        if not model.provider.enabled:
            raise InternalServerException("默认 Supervisor 规划模型的服务商已停用")
        if AIModelTaskType.SUPERVISOR_PLANNING.value not in model.task_types:
            raise InternalServerException("默认模型不支持 Supervisor 规划")
        prompt = await self.prompt_template_repository.get_by_code("supervisor_planning")
        if prompt is None or not prompt.enabled:
            raise InternalServerException("未配置已启用的 supervisor_planning Prompt")
        return model, prompt

    def _available_capabilities(self, granted_permissions: frozenset[str]) -> list[dict[str, object]]:
        """生成当前用户实际可规划的最小能力说明。

        功能：按实时权限过滤能力，并只输出模型规划需要的公开元数据。
        作用：作为 Prompt 中的能力白名单，减少模型提出无权限步骤的概率。
        为什么用它：不把 Service 类名、函数对象和内部实现暴露给模型；即使模型仍编造能力，
        后置校验器也会再次拒绝，形成“输入收窄 + 输出校验”两层保护。
        """
        wildcard = "*" in granted_permissions
        return [
            {
                "code": capability.code,
                "name": capability.name,
                "description": capability.description,
                "risk_level": capability.risk_level.value,
                "read_only": capability.read_only,
                "requires_human_approval": capability.requires_human_approval,
                "arguments_schema": (
                    capability.arguments_model.model_json_schema() if capability.arguments_model is not None else {}
                ),
            }
            for capability in self.registry.list_for_supervisor()
            if wildcard or capability.required_permission in granted_permissions
        ]

    def _build_step_entities(
        self,
        run_id: int,
        plan: SupervisorPlanDTO,
        validation: SupervisorPlanValidationVO,
    ) -> list[SupervisorPlanStep]:
        """把可信计划和校验结果转换成待保存的步骤实体。

        功能：冻结服务端能力风险、权限、审批要求以及每一步初始状态。
        作用：后续执行器只读取这里保存的服务端快照，不相信模型自己声明的风险或权限。
        为什么用它：能力配置可能在计划后发生变化，快照便于审计当时为何允许或阻止；
        未登记能力按 HIGH 风险和 REJECTED 保存，只用于审计，绝不会进入执行器。
        """
        validation_by_step = {item.step_id: item for item in validation.steps}
        entities: list[SupervisorPlanStep] = []
        for step_no, step in enumerate(plan.steps, start=1):
            checked = validation_by_step[step.step_id]
            capability = self.registry.get(step.capability_code)
            if checked.decision == SupervisorStepDecision.READY:
                status = SupervisorExecutionStepStatus.READY
            elif checked.decision == SupervisorStepDecision.BLOCKED_APPROVAL:
                status = SupervisorExecutionStepStatus.WAITING_APPROVAL
            else:
                status = SupervisorExecutionStepStatus.REJECTED
            entities.append(
                SupervisorPlanStep(
                    run_id=run_id,
                    step_no=step_no,
                    step_key=step.step_id,
                    capability_code=step.capability_code,
                    purpose=step.purpose,
                    arguments_snapshot=step.arguments,
                    depends_on=step.depends_on,
                    required_permission=(capability.required_permission if capability is not None else "UNREGISTERED"),
                    risk_level=(capability.risk_level.value if capability is not None else ToolRisk.HIGH.value),
                    decision=checked.decision.value,
                    requires_human_approval=checked.requires_human_approval,
                    status=status.value,
                    error_message="；".join(checked.issues) or None,
                )
            )
        return entities

    async def create_plan(
        self,
        project_id: int,
        payload: SupervisorCreateRunDTO,
        current_user: User,
        granted_permissions: Collection[str],
        *,
        request_id: str | None = None,
    ) -> SupervisorRunDetailVO:
        """创建一次 Supervisor 规划运行并保存候选步骤。

        功能：完成项目权限、上下文安全、AI 配置、Graph 规划、计划校验和事务落库。
        作用：返回的运行只可能是 READY、WAITING_APPROVAL、PLAN_REJECTED 或 FAILED，
        本方法不会执行任何能力。
        为什么用它：先提交 PLANNING 主记录再调用外部模型，模型超时后仍有可查询审计记录；
        Graph 完成后再一次性保存全部步骤和主状态，避免页面看到半份计划。
        """
        if await self.project_repository.get_accessible_project(project_id, current_user) is None:
            raise NotFoundException("项目不存在或无权访问")
        self._ensure_context_safe(payload.business_context)
        # project_id 来自经过 FastAPI 校验和数据权限检查的路径参数，属于服务端可信上下文。
        # 放在最后可以覆盖用户字典中伪造的同名键，模型便能为能力生成正确的项目参数。
        effective_business_context = {**payload.business_context, "project_id": project_id}
        context_json = json.dumps(effective_business_context, ensure_ascii=False, sort_keys=True, default=str)
        if len(context_json) > _MAX_BUSINESS_CONTEXT_CHARS:
            raise BadRequestException(f"业务上下文不能超过 {_MAX_BUSINESS_CONTEXT_CHARS} 个字符")

        permissions = frozenset(str(code) for code in granted_permissions)
        capabilities = self._available_capabilities(permissions)
        if not capabilities:
            raise BadRequestException("当前用户没有可供 Supervisor 规划的能力")
        model, prompt = await self._load_ai_configuration()

        run = SupervisorRun(
            project_id=project_id,
            goal=payload.goal.strip(),
            invocation_source=CapabilityInvocationSource.SUPERVISOR.value,
            status=SupervisorRunStatus.PLANNING.value,
            model_id=model.id,
            requested_by=current_user.id,
            permission_snapshot=sorted(permissions),
            context_snapshot=effective_business_context,
            steps=[],
        )
        self.repository.add_run(run)
        await self.repository.commit()
        await self.repository.refresh(run)

        try:
            graph_result = await self.planning_graph.ainvoke(
                {
                    "goal": run.goal,
                    "business_context_json": context_json,
                    "available_capabilities_json": json.dumps(capabilities, ensure_ascii=False),
                    "validation_feedback": "",
                    "retry_count": 0,
                },
                context=SupervisorPlanningContext(
                    ai_model_repository=self.ai_model_repository,
                    ai_model=model,
                    prompt_template=prompt,
                    usage_context=AIUsageContextDTO(
                        request_id=request_id,
                        user_id=current_user.id,
                        project_id=project_id,
                        task_id=f"supervisor:{run.id}",
                    ),
                    registry=self.registry,
                    granted_permissions=permissions,
                    invocation_source=CapabilityInvocationSource.SUPERVISOR,
                ),
            )
            plan = graph_result.get("plan")
            validation = graph_result.get("validation")
            if not isinstance(plan, SupervisorPlanDTO) or not isinstance(validation, SupervisorPlanValidationVO):
                errors = [str(error) for error in graph_result.get("validation_errors", [])]
                error_message = "；".join(errors[:5]) or "模型未生成可校验的 Supervisor 计划"
                transitioned = await self.repository.transition_run(
                    project_id,
                    run.id,
                    {SupervisorRunStatus.PLANNING},
                    SupervisorRunStatus.PLAN_REJECTED,
                    error_message=error_message,
                )
                if not transitioned:
                    raise ConflictException("Supervisor 运行状态已经变化，请刷新后重试")
                await self.repository.commit()
                persisted = await self.repository.get_run(project_id, run.id)
                if persisted is None:
                    raise InternalServerException("Supervisor 规划记录保存后无法读取")
                return self._run_detail_read(persisted)

            for step_entity in self._build_step_entities(run.id, plan, validation):
                self.repository.add(step_entity)
            if not validation.valid:
                target_status = SupervisorRunStatus.PLAN_REJECTED
            elif validation.requires_human_approval:
                target_status = SupervisorRunStatus.WAITING_APPROVAL
            else:
                target_status = SupervisorRunStatus.READY
            transitioned = await self.repository.transition_run(
                project_id,
                run.id,
                {SupervisorRunStatus.PLANNING},
                target_status,
                error_message=("；".join(validation.issues[:5]) or None),
            )
            if not transitioned:
                raise ConflictException("Supervisor 运行状态已经变化，请刷新后重试")
            await self.repository.commit()
        except Exception as exc:
            await self.repository.rollback()
            await self.repository.transition_run(
                project_id,
                run.id,
                {SupervisorRunStatus.PLANNING},
                SupervisorRunStatus.FAILED,
                error_message=describe_exception(exc)[:2000],
            )
            await self.repository.commit()
            raise

        persisted = await self.repository.get_run(project_id, run.id)
        if persisted is None:
            raise InternalServerException("Supervisor 规划记录保存后无法读取")
        return self._run_detail_read(persisted)

    async def list_runs(
        self,
        project_id: int,
        current_user: User,
        current: int,
        size: int,
        status: SupervisorRunStatus | None,
    ) -> tuple[list[SupervisorRunVO], int]:
        """分页查询当前用户可访问项目中的 Supervisor 运行。

        功能：先校验项目数据权限，再按状态和分页参数读取运行主记录。
        作用：为任务时间线列表提供轻量数据，不加载每条运行的全部步骤。
        为什么用它：列表与详情分开可以避免一次加载大量 JSON 参数和步骤，数据量增长后仍能稳定分页。
        """
        if await self.project_repository.get_accessible_project(project_id, current_user) is None:
            raise NotFoundException("项目不存在或无权访问")
        records, total = await self.repository.list_runs(project_id, current, size, status)
        return [self._run_read(run) for run in records], total

    async def get_run_detail(
        self,
        project_id: int,
        run_id: int,
        current_user: User,
    ) -> SupervisorRunDetailVO:
        """查询项目内一次 Supervisor 运行及全部步骤。"""
        if await self.project_repository.get_accessible_project(project_id, current_user) is None:
            raise NotFoundException("项目不存在或无权访问")
        run = await self.repository.get_run(project_id, run_id)
        if run is None:
            raise NotFoundException("Supervisor 运行不存在")
        return self._run_detail_read(run)

    async def cancel_run(
        self,
        project_id: int,
        run_id: int,
        current_user: User,
    ) -> SupervisorRunDetailVO:
        """取消尚未开始执行的 Supervisor 运行。

        功能：允许发起人、项目负责人、项目管理员或超级管理员取消规划中、就绪或等待审批的运行。
        作用：同时取消仍可取消的步骤和主运行，避免页面出现主任务已取消但步骤仍显示待执行。
        为什么用它：普通项目成员不能取消他人的任务；使用项目角色而不是仅靠按钮权限，
        补上具体数据对象的所有权边界。当前执行器尚未接入，因此 RUNNING 不在本接口取消范围内。
        """
        project = await self.project_repository.get_accessible_project(project_id, current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权访问")
        run = await self.repository.get_run(project_id, run_id, lock=True)
        if run is None:
            raise NotFoundException("Supervisor 运行不存在")

        member = None
        if not current_user.is_superuser and project.owner_id != current_user.id:
            member = await self.project_member_repository.get_member(project_id, current_user.id)
        can_cancel = (
            current_user.is_superuser
            or run.requested_by == current_user.id
            or project.owner_id == current_user.id
            or (
                member is not None
                and member.member_role in {ProjectMemberRole.OWNER.value, ProjectMemberRole.MANAGER.value}
            )
        )
        if not can_cancel:
            raise ForbiddenException("只能取消本人发起的 Supervisor 运行，项目负责人和管理员除外")

        current_status = SupervisorRunStatus(run.status)
        cancellable_statuses = {
            SupervisorRunStatus.PLANNING,
            SupervisorRunStatus.READY,
            SupervisorRunStatus.WAITING_APPROVAL,
        }
        if current_status not in cancellable_statuses:
            raise ConflictException("当前 Supervisor 运行状态不允许取消")

        for step in run.steps:
            step_status = SupervisorExecutionStepStatus(step.status)
            if step_status in {
                SupervisorExecutionStepStatus.PROPOSED,
                SupervisorExecutionStepStatus.READY,
                SupervisorExecutionStepStatus.WAITING_APPROVAL,
            }:
                await self.repository.transition_step(
                    run.id,
                    step.id,
                    {step_status},
                    SupervisorExecutionStepStatus.CANCELLED,
                )
        transitioned = await self.repository.transition_run(
            project_id,
            run.id,
            {current_status},
            SupervisorRunStatus.CANCELLED,
        )
        if not transitioned:
            await self.repository.rollback()
            raise ConflictException("Supervisor 运行状态已经变化，请刷新后重试")
        await self.repository.commit()
        persisted = await self.repository.get_run(project_id, run.id)
        if persisted is None:
            raise InternalServerException("Supervisor 运行取消后无法读取")
        return self._run_detail_read(persisted)

    async def request_execution(
        self,
        project_id: int,
        run_id: int,
        current_user: User,
    ) -> SupervisorRunDetailVO:
        """可靠地提交一条已就绪 Supervisor 运行给后台执行。

        功能：校验项目数据权限和运行控制权，把主运行从 READY 原子推进到 RUNNING，
        同时写入 Supervisor 执行发件箱事件。
        作用：HTTP API 调用本方法后立即返回；发件箱发布器再把事件发送给专用 Celery Worker。
        为什么用它：状态更新与事件写入共享同一个 PostgreSQL 事务，可避免“状态已变但消息没发出”
        或“消息已发送但状态未提交”。实际能力执行不占用 Web 请求连接。
        """
        if self.outbox_repository is None:
            raise InternalServerException("Supervisor 执行发件箱未配置")
        project = await self.project_repository.get_accessible_project(project_id, current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权访问")
        run = await self.repository.get_run(project_id, run_id, lock=True)
        if run is None:
            raise NotFoundException("Supervisor 运行不存在")

        member = None
        if not current_user.is_superuser and project.owner_id != current_user.id:
            member = await self.project_member_repository.get_member(project_id, current_user.id)
        can_execute = (
            current_user.is_superuser
            or run.requested_by == current_user.id
            or project.owner_id == current_user.id
            or (
                member is not None
                and member.member_role in {ProjectMemberRole.OWNER.value, ProjectMemberRole.MANAGER.value}
            )
        )
        if not can_execute:
            raise ForbiddenException("只有发起人、项目负责人或项目管理员可以启动该计划")
        if run.status != SupervisorRunStatus.READY.value:
            if run.status == SupervisorRunStatus.WAITING_APPROVAL.value:
                raise ConflictException("计划仍有步骤等待人工审批，暂时不能启动")
            raise ConflictException(f"当前运行状态 {run.status} 不允许启动执行")
        if not run.steps or any(step.status != SupervisorExecutionStepStatus.READY.value for step in run.steps):
            raise ConflictException("计划步骤尚未全部就绪，请重新生成或完成审批")

        transitioned = await self.repository.transition_run(
            project_id,
            run.id,
            {SupervisorRunStatus.READY},
            SupervisorRunStatus.RUNNING,
        )
        if not transitioned:
            await self.repository.rollback()
            raise ConflictException("Supervisor 运行状态已经变化，请刷新后重试")
        self.outbox_repository.add_pending_event(
            event_type=OutboxEventType.SUPERVISOR_EXECUTION.value,
            aggregate_type=OutboxAggregateType.SUPERVISOR_RUN.value,
            aggregate_id=run.id,
            payload={"project_id": project_id, "run_id": run.id},
        )
        await self.repository.commit()

        persisted = await self.repository.get_run(project_id, run.id)
        if persisted is None:
            raise InternalServerException("Supervisor 执行任务提交后无法读取")
        return self._run_detail_read(persisted)

    async def decide_step_approval(
        self,
        project_id: int,
        run_id: int,
        step_id: int,
        payload: SupervisorApprovalDTO,
        current_user: User,
    ) -> SupervisorRunDetailVO:
        """审批一个中高风险步骤，并在最后一项获批后自动恢复执行。

        功能：锁定运行、禁止普通发起人自批、记录审批人和意见；驳回时取消整条计划，
        批准最后一个等待步骤时在同一事务内写入执行发件箱。
        作用：这是模型计划与真实写操作之间的人工作业关卡。审批接口只改变受控状态，
        实际业务调用仍由 Supervisor Worker 完成。
        为什么用它：审批结果、运行状态和待发布事件共享一个 PostgreSQL 事务，避免
        “页面显示已批准但任务没有发出”；通过步骤 ID 定位，审计时可以还原谁批准了什么。
        """
        if self.outbox_repository is None:
            raise InternalServerException("Supervisor 执行发件箱未配置")
        project = await self.project_repository.get_accessible_project(project_id, current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权访问")
        run = await self.repository.get_run(project_id, run_id, lock=True)
        if run is None:
            raise NotFoundException("Supervisor 运行不存在")
        if run.status != SupervisorRunStatus.WAITING_APPROVAL.value:
            raise ConflictException("该运行当前没有等待审批的步骤")
        step = next((item for item in run.steps if item.id == step_id), None)
        if step is None:
            raise NotFoundException("Supervisor 步骤不存在")
        if step.status != SupervisorExecutionStepStatus.WAITING_APPROVAL.value:
            raise ConflictException("该步骤已经处理或不需要审批")
        if run.requested_by == current_user.id and not current_user.is_superuser:
            raise ForbiddenException("中高风险步骤不能由计划发起人自行审批")

        if payload.decision == SupervisorApprovalDecision.REJECTED:
            transitioned = await self.repository.transition_step(
                run.id,
                step.id,
                {SupervisorExecutionStepStatus.WAITING_APPROVAL},
                SupervisorExecutionStepStatus.CANCELLED,
                error_message="人工审批已驳回",
                approval_decided_by=current_user.id,
                approval_decision=payload.decision.value,
                approval_comment=payload.comment.strip(),
            )
            if not transitioned:
                await self.repository.rollback()
                raise ConflictException("步骤审批状态已经变化，请刷新后重试")
            for other in run.steps:
                if other.id == step.id:
                    continue
                other_status = SupervisorExecutionStepStatus(other.status)
                if other_status in {
                    SupervisorExecutionStepStatus.READY,
                    SupervisorExecutionStepStatus.WAITING_APPROVAL,
                }:
                    await self.repository.transition_step(
                        run.id,
                        other.id,
                        {other_status},
                        SupervisorExecutionStepStatus.CANCELLED,
                        error_message="同一计划中的风险步骤被人工驳回",
                    )
            await self.repository.transition_run(
                project_id,
                run.id,
                {SupervisorRunStatus.WAITING_APPROVAL},
                SupervisorRunStatus.CANCELLED,
                error_message="计划中的风险步骤被人工驳回",
            )
        else:
            transitioned = await self.repository.transition_step(
                run.id,
                step.id,
                {SupervisorExecutionStepStatus.WAITING_APPROVAL},
                SupervisorExecutionStepStatus.READY,
                approval_decided_by=current_user.id,
                approval_decision=payload.decision.value,
                approval_comment=payload.comment.strip(),
            )
            if not transitioned:
                await self.repository.rollback()
                raise ConflictException("步骤审批状态已经变化，请刷新后重试")
            remaining_waiting = any(
                other.id != step.id
                and other.status == SupervisorExecutionStepStatus.WAITING_APPROVAL.value
                for other in run.steps
            )
            if not remaining_waiting:
                ready = await self.repository.transition_run(
                    project_id,
                    run.id,
                    {SupervisorRunStatus.WAITING_APPROVAL},
                    SupervisorRunStatus.READY,
                )
                running = ready and await self.repository.transition_run(
                    project_id,
                    run.id,
                    {SupervisorRunStatus.READY},
                    SupervisorRunStatus.RUNNING,
                )
                if not running:
                    await self.repository.rollback()
                    raise ConflictException("运行审批状态已经变化，请刷新后重试")
                self.outbox_repository.add_pending_event(
                    event_type=OutboxEventType.SUPERVISOR_EXECUTION.value,
                    aggregate_type=OutboxAggregateType.SUPERVISOR_RUN.value,
                    aggregate_id=run.id,
                    payload={"project_id": project_id, "run_id": run.id},
                )

        await self.repository.commit()
        persisted = await self.repository.get_run(project_id, run.id)
        if persisted is None:
            raise InternalServerException("Supervisor 审批完成后无法读取")
        return self._run_detail_read(persisted)
