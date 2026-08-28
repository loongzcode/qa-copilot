"""Supervisor 计划步骤的可恢复顺序执行服务。"""

from __future__ import annotations

from app.agents.supervisor_capabilities import SUPERVISOR_CAPABILITY_REGISTRY, AgentCapabilityRegistry
from app.core.constants import SupervisorExecutionStepStatus, SupervisorRunStatus
from app.core.deps import get_permission_codes
from app.exceptions.errors import describe_exception
from app.repositories.auth_repository import AuthRepository
from app.repositories.supervisor_repository import SupervisorRepository
from app.services.supervisor_capability_executor import SupervisorCapabilityExecutor


class SupervisorExecutionService:
    """按计划顺序执行已经通过确定性安全校验的步骤。

    功能：恢复运行记录、重新检查用户实时权限、验证步骤依赖、逐项调用能力并保存结果。
    作用：由 ``supervisor.execute_run`` Celery 任务调用；HTTP 请求只负责可靠地提交任务，
    不在请求线程里等待整条计划完成。
    为什么用它：每一步开始和结束都单独提交，Worker 意外退出后可以从已成功步骤之后恢复；
    当前只开放幂等的只读能力，重复消费不会产生写入副作用。
    """

    def __init__(
        self,
        repository: SupervisorRepository,
        auth_repository: AuthRepository,
        capability_executor: SupervisorCapabilityExecutor,
        *,
        registry: AgentCapabilityRegistry = SUPERVISOR_CAPABILITY_REGISTRY,
    ) -> None:
        self.repository = repository
        self.auth_repository = auth_repository
        self.capability_executor = capability_executor
        self.registry = registry

    async def _fail_run(self, project_id: int, run_id: int, failed_step_id: int, error_message: str) -> None:
        """把当前步骤、后续步骤和主运行收口到一致的失败状态。

        功能：当前 RUNNING 步骤标记 FAILED，尚未开始的 READY 步骤标记 SKIPPED，主运行标记 FAILED。
        作用：保证前端不会看到“主任务失败但后续步骤仍待执行”的矛盾状态。
        为什么用它：这里只读能力没有可回滚副作用，因此失败补偿是停止传播并保存现场；
        将来接入写能力时，还需在能力定义中增加真正的业务回滚或补偿操作。
        """
        run = await self.repository.get_run(project_id, run_id)
        if run is None:
            return
        # 逆序补偿已经成功的写步骤，顺序与执行相反。补偿只能保证“能安全撤销的尽量撤销”，
        # 已被下游 Worker 领取的任务不能伪装成数据库事务回滚，结果会留在快照供人工核对。
        for succeeded_step in reversed(run.steps):
            if succeeded_step.status != SupervisorExecutionStepStatus.SUCCEEDED.value:
                continue
            capability = self.registry.get(succeeded_step.capability_code)
            if capability is None or capability.read_only:
                continue
            compensation = await self.capability_executor.compensate(
                succeeded_step.capability_code,
                succeeded_step.id,
            )
            succeeded_step.result_snapshot = {
                **dict(succeeded_step.result_snapshot),
                "compensation": compensation,
            }
        for step in run.steps:
            if step.id == failed_step_id and step.status == SupervisorExecutionStepStatus.RUNNING.value:
                await self.repository.transition_step(
                    run_id,
                    step.id,
                    {SupervisorExecutionStepStatus.RUNNING},
                    SupervisorExecutionStepStatus.FAILED,
                    error_message=error_message,
                )
            elif step.status == SupervisorExecutionStepStatus.READY.value:
                await self.repository.transition_step(
                    run_id,
                    step.id,
                    {SupervisorExecutionStepStatus.READY},
                    SupervisorExecutionStepStatus.SKIPPED,
                    error_message="前置步骤失败，未继续执行",
                )
        await self.repository.transition_run(
            project_id,
            run_id,
            {SupervisorRunStatus.RUNNING},
            SupervisorRunStatus.FAILED,
            error_message=error_message,
        )
        await self.repository.commit()

    async def execute(self, project_id: int, run_id: int) -> bool:
        """执行或恢复一条已进入 RUNNING 状态的 Supervisor 运行。

        功能：跳过已成功步骤，从第一个 READY 或因 Worker 中断而停留在 RUNNING 的步骤继续。
        作用：支持 Celery 的至少一次投递语义；同一任务重新投递时不会重复创建计划或步骤。
        为什么用它：后台消息可能重复，执行状态必须以 PostgreSQL 为事实来源；把每一步结果落库后再
        进入下一步，比只在内存中跑完整个循环更容易恢复和审计。
        """
        run = await self.repository.get_run(project_id, run_id)
        if run is None:
            return False
        if run.status == SupervisorRunStatus.SUCCEEDED.value:
            return True
        if run.status != SupervisorRunStatus.RUNNING.value or run.requested_by is None:
            return False

        actor = await self.auth_repository.get_by_id(run.requested_by, with_permissions=True)
        if actor is None or not actor.is_active:
            await self.repository.transition_run(
                project_id,
                run_id,
                {SupervisorRunStatus.RUNNING},
                SupervisorRunStatus.FAILED,
                error_message="原计划发起用户不存在或已停用",
            )
            await self.repository.commit()
            return False
        permissions = frozenset(str(code) for code in get_permission_codes(actor) if code)
        completed_step_keys = {
            step.step_key
            for step in run.steps
            if step.status == SupervisorExecutionStepStatus.SUCCEEDED.value
        }
        result_steps: list[dict[str, object]] = []

        for step in sorted(run.steps, key=lambda item: item.step_no):
            if step.status == SupervisorExecutionStepStatus.SUCCEEDED.value:
                continue
            if step.status not in {
                SupervisorExecutionStepStatus.READY.value,
                SupervisorExecutionStepStatus.RUNNING.value,
            }:
                message = f"步骤 {step.step_key} 当前状态 {step.status} 不允许执行"
                await self.repository.transition_run(
                    project_id,
                    run_id,
                    {SupervisorRunStatus.RUNNING},
                    SupervisorRunStatus.FAILED,
                    error_message=message,
                )
                await self.repository.commit()
                return False

            if step.status == SupervisorExecutionStepStatus.READY.value:
                started = await self.repository.transition_step(
                    run_id,
                    step.id,
                    {SupervisorExecutionStepStatus.READY},
                    SupervisorExecutionStepStatus.RUNNING,
                )
                if not started:
                    await self.repository.rollback()
                    return False
                await self.repository.update_running_progress(project_id, run_id, step.step_no)
                await self.repository.commit()

            try:
                missing_dependencies = [key for key in step.depends_on if key not in completed_step_keys]
                if missing_dependencies:
                    raise RuntimeError(f"前置步骤尚未成功：{', '.join(missing_dependencies)}")
                result = await self.capability_executor.execute(
                    capability_code=step.capability_code,
                    arguments=dict(step.arguments_snapshot),
                    project_id=project_id,
                    current_user=actor,
                    granted_permissions=permissions,
                    frozen_required_permission=step.required_permission,
                    supervisor_step_id=step.id,
                    approval_decision=getattr(step, "approval_decision", None),
                )
                completed = await self.repository.transition_step(
                    run_id,
                    step.id,
                    {SupervisorExecutionStepStatus.RUNNING},
                    SupervisorExecutionStepStatus.SUCCEEDED,
                    result_snapshot=result,
                )
                if not completed:
                    raise RuntimeError("步骤状态已被其他执行者修改")
                await self.repository.commit()
            except Exception as exc:
                await self.repository.rollback()
                error_message = describe_exception(exc)[:2000]
                await self._fail_run(project_id, run_id, step.id, error_message)
                return False

            completed_step_keys.add(step.step_key)
            result_steps.append(
                {
                    "stepKey": step.step_key,
                    "capabilityCode": step.capability_code,
                    "status": SupervisorExecutionStepStatus.SUCCEEDED.value,
                }
            )

        completed_run = await self.repository.transition_run(
            project_id,
            run_id,
            {SupervisorRunStatus.RUNNING},
            SupervisorRunStatus.SUCCEEDED,
            current_step_no=len(run.steps),
            result_summary={"executedStepCount": len(completed_step_keys), "steps": result_steps},
        )
        if not completed_run:
            await self.repository.rollback()
            return False
        await self.repository.commit()
        return True
