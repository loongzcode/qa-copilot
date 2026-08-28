"""把 Supervisor 白名单能力安全地转发给现有业务 Service。"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.agents.supervisor_capabilities import (
    SUPERVISOR_CAPABILITY_REGISTRY,
    AgentCapabilityRegistry,
    GenerateMissingCasesArguments,
    QualityDeliveryStatusArguments,
)
from app.exceptions import BadRequestException, ForbiddenException, InternalServerException
from app.models import User
from app.services.quality_delivery_service import QualityDeliveryService
from app.services.test_cases_service import TestCasesService


class SupervisorCapabilityExecutor:
    """执行能力目录中已经显式登记的业务操作。

    功能：重新校验能力、参数、项目边界和实时权限，再调用对应业务 Service。
    作用：它是 Supervisor 计划步骤与现有业务代码之间唯一的执行入口；模型提供的
    ``service_operation`` 或任意函数名不会被直接执行。
    为什么用它：显式的 ``if`` 映射虽然比反射多几行代码，但新增能力必须经过代码评审，
    不会因为模型编造函数名或数据库内容被修改而调用任意 Python 方法。
    """

    def __init__(
        self,
        quality_delivery_service: QualityDeliveryService,
        test_cases_service: TestCasesService | None = None,
        *,
        registry: AgentCapabilityRegistry = SUPERVISOR_CAPABILITY_REGISTRY,
    ) -> None:
        self.quality_delivery_service = quality_delivery_service
        self.test_cases_service = test_cases_service
        self.registry = registry

    async def execute(
        self,
        *,
        capability_code: str,
        arguments: dict[str, Any],
        project_id: int,
        current_user: User,
        granted_permissions: frozenset[str],
        frozen_required_permission: str,
        supervisor_step_id: int = 0,
        approval_decision: str | None = None,
    ) -> dict[str, Any]:
        """校验并执行一个低风险、无需人工审批的 Supervisor 能力。

        功能：核对实时能力定义和规划快照，使用 Pydantic 重新校验参数后返回 JSON 结果。
        作用：Worker 每执行一个步骤都会调用本方法，不能绕过项目数据权限或业务 Service。
        为什么用它：规划到执行之间用户权限、能力配置都可能变化，所以不能只相信规划时的快照；
        参数也必须在执行前再验证一次，防止数据库被人工修改后越权访问其他项目。
        """
        capability = self.registry.get(capability_code)
        if capability is None or not capability.supervisor_enabled:
            raise BadRequestException(f"能力不存在或已停止向 Supervisor 开放：{capability_code}")
        if capability.required_permission != frozen_required_permission:
            raise BadRequestException("能力权限定义在规划后发生变化，请重新生成计划")
        if "*" not in granted_permissions and capability.required_permission not in granted_permissions:
            raise ForbiddenException(f"执行时已缺少能力权限：{capability.required_permission}")
        if capability.requires_human_approval and approval_decision != "APPROVED":
            raise ForbiddenException("该能力尚未获得人工批准，不能执行")
        if capability.arguments_model is None:
            raise InternalServerException(f"能力没有配置参数模型：{capability_code}")
        try:
            validated_arguments = capability.arguments_model.model_validate(arguments)
        except ValidationError as exc:
            raise BadRequestException(f"能力参数校验失败：{exc}") from exc

        if capability_code == "quality_delivery.get_status":
            if not isinstance(validated_arguments, QualityDeliveryStatusArguments):
                raise InternalServerException("质量交付状态能力的参数模型配置错误")
            if validated_arguments.project_id != project_id:
                raise ForbiddenException("能力参数中的项目 ID 与 Supervisor 运行不一致")
            result = await self.quality_delivery_service.get_status(
                validated_arguments.project_id,
                validated_arguments.requirement_id,
                current_user,
            )
            return result.model_dump(mode="json", by_alias=True)

        if capability_code == "test_case.generate_missing":
            if not isinstance(validated_arguments, GenerateMissingCasesArguments):
                raise InternalServerException("缺失用例生成能力的参数模型配置错误")
            if validated_arguments.project_id != project_id:
                raise ForbiddenException("能力参数中的项目 ID 与 Supervisor 运行不一致")
            if self.test_cases_service is None:
                raise InternalServerException("缺失用例生成能力的业务服务未配置")
            task = await self.test_cases_service.submit_generation(
                validated_arguments.project_id,
                validated_arguments.requirement_id,
                current_user,
                supervisor_step_id=supervisor_step_id,
            )
            return task.model_dump(mode="json", by_alias=True)

        raise InternalServerException(f"能力已登记但尚未接入执行适配器：{capability_code}")

    async def compensate(self, capability_code: str, supervisor_step_id: int) -> dict[str, Any]:
        """按能力白名单执行 best-effort（尽最大努力）补偿，而不是反射调用任意方法。"""
        if capability_code == "test_case.generate_missing":
            if self.test_cases_service is None:
                return {"status": "NOT_APPLIED", "reason": "用例服务未配置"}
            cancelled = await self.test_cases_service.compensate_supervisor_generation(
                supervisor_step_id
            )
            return {
                "status": "COMPENSATED" if cancelled else "NOT_APPLIED",
                "reason": "任务已在领取前取消" if cancelled else "任务已开始或已经进入终态，不能自动撤销",
            }
        return {"status": "NOT_REQUIRED", "reason": "只读能力没有写入副作用"}
