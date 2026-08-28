"""自动化执行报告的 PostgreSQL 集成冒烟测试。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.constants import AutomationExecutionStatus  # noqa: E402
from app.core.database import AsyncSessionFactory, engine  # noqa: E402
from app.models import (  # noqa: E402
    AutomationDefinition,
    AutomationExecutionStepResult,
    AutomationExecutionTask,
    TestCase,
    TestEnvironment,
    TestProjects,
)
from app.repositories.automation_execution_tasks_repository import (  # noqa: E402
    AutomationExecutionTasksRepository,
)


async def main() -> None:
    """创建临时运行任务，原子保存两个步骤，读取报告后级联清理。"""
    task_id: int | None = None
    definition_id: int | None = None
    environment_id: int | None = None
    test_case_id: int | None = None
    try:
        async with AsyncSessionFactory() as session:
            project_id = await session.scalar(select(TestProjects.id).where(TestProjects.deleted_at.is_(None)).limit(1))
            if project_id is None:
                raise RuntimeError("集成测试至少需要一个测试项目")
            suffix = uuid4().hex[:10]
            test_case = TestCase(
                project_id=project_id,
                case_code=f"REPORT-SMOKE-{suffix}",
                title="自动化报告集成测试用例",
                case_type="API",
                priority="P2",
                preconditions="",
                expected_summary="",
                status="PUBLISHED",
                source="MANUAL",
                automatable=True,
                version=1,
            )
            environment = TestEnvironment(
                project_id=project_id,
                name=f"报告集成环境-{suffix}",
                environment_type="TEST",
                base_url="http://127.0.0.1",
                allowed_hosts=["127.0.0.1"],
                headers={},
                encrypted_variables="",
                enabled=True,
            )
            session.add_all([test_case, environment])
            await session.flush()
            test_case_id = test_case.id
            environment_id = environment.id
            definition = AutomationDefinition(
                project_id=project_id,
                test_case_id=test_case.id,
                name="自动化报告集成定义",
                version=1,
                status="APPROVED",
                schema_version="1.0",
                source_case_version=1,
                definition={"schemaVersion": "1.0", "steps": []},
                definition_hash="0" * 64,
            )
            session.add(definition)
            await session.flush()
            definition_id = definition.id
            task = AutomationExecutionTask(
                project_id=project_id,
                definition_id=definition.id,
                environment_id=environment.id,
                status="RUNNING",
                progress=30,
                current_stage="RUNNING_PYTEST",
                timeout_seconds=30,
                definition_hash=definition.definition_hash,
                environment_updated_at=environment.updated_at,
            )
            session.add(task)
            await session.commit()
            task_id = task.id

        async with AsyncSessionFactory() as session:
            repository = AutomationExecutionTasksRepository(session)
            saved = await repository.finish_task(
                task_id,
                status=AutomationExecutionStatus.FAILED,
                result_summary={"success": False, "passedSteps": 1, "failedSteps": 1, "skippedSteps": 0},
                error_message="断言 STATUS_CODE 未通过",
                step_results=[
                    {
                        "stepNo": 1,
                        "name": "登录",
                        "status": "PASSED",
                        "method": "POST",
                        "path": "/login",
                        "statusCode": 200,
                        "durationMs": 20,
                        "requestSummary": {"bodyType": "JSON"},
                        "responseSummary": {"statusCode": 200},
                        "assertions": [{"type": "STATUS_CODE", "passed": True}],
                    },
                    {
                        "stepNo": 2,
                        "name": "查询",
                        "status": "FAILED",
                        "method": "GET",
                        "path": "/items",
                        "statusCode": 500,
                        "durationMs": 30,
                        "requestSummary": {"bodyType": "NONE"},
                        "responseSummary": {"statusCode": 500},
                        "assertions": [{"type": "STATUS_CODE", "passed": False}],
                        "errorMessage": "断言 STATUS_CODE 未通过",
                    },
                ],
            )
            assert saved is True
            task, steps = await repository.get_report(project_id, task_id)
            assert task is not None and task.status == "FAILED"
            assert [step.status for step in steps] == ["PASSED", "FAILED"]
            assert steps[1].response_summary == {"statusCode": 500}
            assert "body" not in steps[1].response_summary
        print("自动化执行报告数据库集成验证通过")
    finally:
        if task_id is not None:
            async with AsyncSessionFactory() as session:
                await session.execute(
                    delete(AutomationExecutionStepResult).where(
                        AutomationExecutionStepResult.execution_task_id == task_id
                    )
                )
                await session.execute(delete(AutomationExecutionTask).where(AutomationExecutionTask.id == task_id))
                if definition_id is not None:
                    await session.execute(
                        delete(AutomationDefinition).where(AutomationDefinition.id == definition_id)
                    )
                if environment_id is not None:
                    await session.execute(delete(TestEnvironment).where(TestEnvironment.id == environment_id))
                if test_case_id is not None:
                    await session.execute(delete(TestCase).where(TestCase.id == test_case_id))
                await session.commit()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
