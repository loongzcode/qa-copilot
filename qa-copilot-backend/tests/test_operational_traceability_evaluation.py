from scripts.evaluate_operational_traceability import (
    _automation_missing,
    _high_risk_tool_missing,
)


def test_complete_automation_task_has_no_missing_evidence() -> None:
    row = {
        "status": "PASSED",
        "definition_exists": True,
        "environment_exists": True,
        "requested_by": 1,
        "outbox_event_exists": True,
        "celery_task_id": "task-1",
        "started_at": "start",
        "finished_at": "finish",
        "result_summary": {"success": True},
        "error_message": None,
        "step_result_count": 1,
    }

    assert _automation_missing(row) == []


def test_complete_high_risk_task_has_full_approval_audit() -> None:
    row = {
        "status": "SUCCEEDED",
        "requested_by": 1,
        "preview_hash": "hash",
        "preview_data": {"changes": []},
        "result_data": {"success": True},
        "error_message": None,
        "started_at": "start",
        "finished_at": "finish",
        "has_create_log": True,
        "has_preview_log": True,
        "has_approval_log": True,
        "has_execute_log": True,
        "has_rollback_log": False,
        "has_matching_approval": True,
    }

    assert _high_risk_tool_missing(row) == []
