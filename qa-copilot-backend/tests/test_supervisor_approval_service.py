"""Supervisor 人工审批与自动恢复执行专项测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.core.constants import (
    SupervisorApprovalDecision,
    SupervisorExecutionStepStatus,
    SupervisorRunStatus,
)
from app.schemas.dto.supervisor import SupervisorApprovalDTO
from app.services.supervisor_service import SupervisorService


async def test_last_approval_writes_execution_outbox_in_same_transaction() -> None:
    """最后一个风险步骤获批后，应把运行推进到 RUNNING 并写入执行事件。"""
    step = SimpleNamespace(
        id=101,
        status=SupervisorExecutionStepStatus.WAITING_APPROVAL.value,
    )
    run = SimpleNamespace(
        id=31,
        requested_by=9,
        status=SupervisorRunStatus.WAITING_APPROVAL.value,
        steps=[step],
    )
    persisted = SimpleNamespace(id=31)
    repository = SimpleNamespace(
        get_run=AsyncMock(side_effect=[run, persisted]),
        transition_step=AsyncMock(return_value=True),
        transition_run=AsyncMock(return_value=True),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    outbox_repository = SimpleNamespace(add_pending_event=Mock())
    service = SupervisorService(
        repository=repository,
        project_repository=SimpleNamespace(
            get_accessible_project=AsyncMock(return_value=SimpleNamespace(id=8))
        ),
        project_member_repository=SimpleNamespace(),
        ai_model_repository=SimpleNamespace(),
        prompt_template_repository=SimpleNamespace(),
        outbox_repository=outbox_repository,
    )
    service._run_detail_read = lambda value: value  # type: ignore[method-assign]
    approver = SimpleNamespace(id=20, is_superuser=False)

    result = await service.decide_step_approval(
        8,
        31,
        101,
        SupervisorApprovalDTO(
            decision=SupervisorApprovalDecision.APPROVED,
            comment="已核对影响范围",
        ),
        approver,
    )

    assert result is persisted
    assert repository.transition_run.await_count == 2
    assert repository.transition_run.await_args_list[0].args[3] == SupervisorRunStatus.READY
    assert repository.transition_run.await_args_list[1].args[3] == SupervisorRunStatus.RUNNING
    outbox_repository.add_pending_event.assert_called_once()
    repository.commit.assert_awaited_once()
