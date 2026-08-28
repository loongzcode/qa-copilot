"""Supervisor 能力适配器和顺序执行器的专项测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from app.core.constants import SupervisorExecutionStepStatus, SupervisorRunStatus
from app.core.permissions import Permission
from app.exceptions import ForbiddenException
from app.services.supervisor_capability_executor import SupervisorCapabilityExecutor
from app.services.supervisor_execution_service import SupervisorExecutionService


async def test_capability_executor_invokes_quality_delivery_service() -> None:
    """已授权能力必须通过业务 Service 查询，且把 CamelModel 结果转成 JSON 快照。"""
    result_vo = SimpleNamespace(
        model_dump=Mock(return_value={"stage": "HUMAN_REQUIREMENT_REVIEW", "nextAction": "确认需求点"})
    )
    quality_delivery_service = SimpleNamespace(get_status=AsyncMock(return_value=result_vo))
    executor = SupervisorCapabilityExecutor(quality_delivery_service)
    user = SimpleNamespace(id=9)

    result = await executor.execute(
        capability_code="quality_delivery.get_status",
        arguments={"project_id": 8, "requirement_id": 12},
        project_id=8,
        current_user=user,
        granted_permissions=frozenset({Permission.REQUIREMENT_VIEW}),
        frozen_required_permission=Permission.REQUIREMENT_VIEW,
    )

    assert result["stage"] == "HUMAN_REQUIREMENT_REVIEW"
    quality_delivery_service.get_status.assert_awaited_once_with(8, 12, user)
    result_vo.model_dump.assert_called_once_with(mode="json", by_alias=True)


async def test_capability_executor_rejects_cross_project_arguments() -> None:
    """即使模型参数格式正确，也不能借另一个项目 ID 绕过当前运行的数据边界。"""
    executor = SupervisorCapabilityExecutor(SimpleNamespace(get_status=AsyncMock()))

    with pytest.raises(ForbiddenException, match="项目 ID"):
        await executor.execute(
            capability_code="quality_delivery.get_status",
            arguments={"project_id": 99, "requirement_id": 12},
            project_id=8,
            current_user=SimpleNamespace(id=9),
            granted_permissions=frozenset({Permission.REQUIREMENT_VIEW}),
            frozen_required_permission=Permission.REQUIREMENT_VIEW,
        )


async def test_write_capability_requires_approval_and_forwards_idempotency_key() -> None:
    """写能力未批准时必须拒绝，批准后把 Supervisor 步骤 ID 传给业务 Service。"""
    task_vo = SimpleNamespace(model_dump=Mock(return_value={"id": 77, "status": "PENDING"}))
    test_cases_service = SimpleNamespace(submit_generation=AsyncMock(return_value=task_vo))
    executor = SupervisorCapabilityExecutor(
        SimpleNamespace(get_status=AsyncMock()),
        test_cases_service,
    )
    kwargs = {
        "capability_code": "test_case.generate_missing",
        "arguments": {"project_id": 8, "requirement_id": 12},
        "project_id": 8,
        "current_user": SimpleNamespace(id=9),
        "granted_permissions": frozenset({Permission.TEST_CASE_GENERATE}),
        "frozen_required_permission": Permission.TEST_CASE_GENERATE,
        "supervisor_step_id": 101,
    }

    with pytest.raises(ForbiddenException, match="尚未获得人工批准"):
        await executor.execute(**kwargs, approval_decision=None)

    result = await executor.execute(**kwargs, approval_decision="APPROVED")

    assert result == {"id": 77, "status": "PENDING"}
    test_cases_service.submit_generation.assert_awaited_once_with(
        8,
        12,
        kwargs["current_user"],
        supervisor_step_id=101,
    )


async def test_execution_service_runs_steps_in_dependency_order() -> None:
    """执行器应跳过已完成步骤，并只在前置步骤成功后执行后续步骤。"""
    steps = [
        SimpleNamespace(
            id=101,
            step_no=1,
            step_key="check_requirement",
            capability_code="quality_delivery.get_status",
            arguments_snapshot={"project_id": 8, "requirement_id": 12},
            depends_on=[],
            required_permission=Permission.REQUIREMENT_VIEW,
            status=SupervisorExecutionStepStatus.READY.value,
        ),
        SimpleNamespace(
            id=102,
            step_no=2,
            step_key="check_again",
            capability_code="quality_delivery.get_status",
            arguments_snapshot={"project_id": 8, "requirement_id": 12},
            depends_on=["check_requirement"],
            required_permission=Permission.REQUIREMENT_VIEW,
            status=SupervisorExecutionStepStatus.READY.value,
        ),
    ]
    run = SimpleNamespace(
        id=31,
        project_id=8,
        requested_by=9,
        status=SupervisorRunStatus.RUNNING.value,
        steps=steps,
    )
    repository = SimpleNamespace(
        get_run=AsyncMock(return_value=run),
        transition_step=AsyncMock(return_value=True),
        update_running_progress=AsyncMock(return_value=True),
        transition_run=AsyncMock(return_value=True),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    actor = SimpleNamespace(id=9, is_active=True, is_superuser=True, roles=[])
    auth_repository = SimpleNamespace(get_by_id=AsyncMock(return_value=actor))
    capability_executor = SimpleNamespace(
        execute=AsyncMock(side_effect=[{"stage": "ONE"}, {"stage": "TWO"}])
    )
    service = SupervisorExecutionService(repository, auth_repository, capability_executor)

    succeeded = await service.execute(8, 31)

    assert succeeded is True
    assert capability_executor.execute.await_count == 2
    assert repository.update_running_progress.await_args_list[0].args == (8, 31, 1)
    assert repository.update_running_progress.await_args_list[1].args == (8, 31, 2)
    final_transition = repository.transition_run.await_args
    assert final_transition.args[:4] == (
        8,
        31,
        {SupervisorRunStatus.RUNNING},
        SupervisorRunStatus.SUCCEEDED,
    )
    assert final_transition.kwargs["result_summary"]["executedStepCount"] == 2
