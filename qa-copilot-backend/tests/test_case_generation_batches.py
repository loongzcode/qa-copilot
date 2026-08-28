"""测试用例分批生成执行逻辑的单元测试。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import app.services.case_generation_execution_service as execution_module
import pytest
from app.agents.case_generation_schemas import CaseGenerationOutput
from app.models import AIModel, AIProvider, PromptTemplate
from app.repositories.ai_model_repository import AIModelRepository
from app.services.case_generation_execution_service import (
    CaseGenerationExecutionService,
)


def _generated_case(requirement_item_id: int) -> dict[str, object]:
    """为指定需求点构造一条最小但完整的模型输出。"""
    return {
        "local_id": f"case-{requirement_item_id}",
        "title": f"需求点 {requirement_item_id} 正常流程",
        "case_type": "FUNCTIONAL",
        "priority": "P1",
        "preconditions": "用户已登录",
        "expected_summary": "操作成功",
        "automatable": True,
        "requirement_item_ids": [requirement_item_id],
        "generation_reason": "补齐覆盖缺口",
        "source_case_ids": [],
        "confidence": 0.9,
        "tags": [],
        "steps": [
            {
                "step_no": 1,
                "action": "执行操作",
                "test_data": None,
                "expected_result": "操作成功",
            }
        ],
    }


@pytest.mark.asyncio
async def test_generate_case_batches_updates_progress_and_merges_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """五个缺口按每批两个拆为三批，并合并为唯一的最终结果。"""
    repository = SimpleNamespace(commit=AsyncMock())
    ai_model_repository = AIModelRepository(SimpleNamespace())
    service = CaseGenerationExecutionService(
        repository=repository,
        requirements_repository=SimpleNamespace(),
        ai_model_repository=ai_model_repository,
        prompt_template_repository=SimpleNamespace(),
        coverage_service=SimpleNamespace(),
    )
    service._collect_reference_cases = AsyncMock(  # type: ignore[method-assign]
        return_value=([], [])
    )
    monkeypatch.setattr(
        execution_module.settings,
        "case_generation_batch_size",
        2,
    )

    graph_calls: list[list[int]] = []

    async def fake_ainvoke(state, *, context):
        del context
        batch_gaps = json.loads(state["gaps_json"])
        requirement_ids = [
            int(gap["requirement_item_id"])
            for gap in batch_gaps
        ]
        graph_calls.append(requirement_ids)
        return {
            "generation_output": CaseGenerationOutput.model_validate(
                {
                    "cases": [
                        _generated_case(requirement_id)
                        for requirement_id in requirement_ids
                    ],
                    "warnings": [],
                }
            ),
            "retry_count": 0,
        }

    monkeypatch.setattr(
        execution_module,
        "CASE_GENERATION_GRAPH",
        SimpleNamespace(ainvoke=fake_ainvoke),
    )
    task = SimpleNamespace(id=9, requested_by=3, progress=55, current_stage="")
    provider = AIProvider()
    model = AIModel()
    model.provider = provider
    prompt = PromptTemplate()
    gaps = [
        {"requirement_item_id": requirement_id}
        for requirement_id in range(1, 6)
    ]

    output, references, retry_count, batch_count = (
        await service._generate_case_batches(
            task=task,
            project_id=8,
            module_id=None,
            gaps=gaps,
            model=model,
            prompt=prompt,
        )
    )

    assert graph_calls == [[1, 2], [3, 4], [5]]
    assert batch_count == 3
    assert retry_count == 0
    assert references == []
    assert len(output.cases) == 5
    assert len({case.local_id for case in output.cases}) == 5
    assert task.current_stage == "GENERATING_CASES_3_OF_3"
    assert task.progress == 80
    assert repository.commit.await_count == 3


@pytest.mark.asyncio
async def test_collect_reference_cases_merges_standard_case_knowledge() -> None:
    """存在标准用例文档时应与正式用例候选一起进入生成参考，并保留切片来源。"""
    repository = SimpleNamespace(
        search_published_cases=AsyncMock(return_value=[]),
        search_standard_case_chunks=AsyncMock(
            return_value=[
                {
                    "chunk_id": 31,
                    "document_id": 7,
                    "document_title": "支付标准用例库",
                    "section_title": "退款异常场景",
                    "page_no": 3,
                    "content": "退款金额超过原订单金额时应拒绝并返回业务错误码。",
                    "retrieval_score": 0.86,
                }
            ]
        ),
    )
    service = CaseGenerationExecutionService(
        repository=repository,
        requirements_repository=SimpleNamespace(),
        ai_model_repository=AIModelRepository(SimpleNamespace()),
        prompt_template_repository=SimpleNamespace(),
        coverage_service=SimpleNamespace(),
    )

    references, signatures = await service._collect_reference_cases(
        8,
        2,
        [
            {
                "title": "退款金额校验",
                "description": "退款不可超过订单金额",
                "acceptance_criteria": "返回明确错误码",
            }
        ],
    )

    assert signatures == []
    assert references == [
        {
            "reference_type": "STANDARD_CASE_KNOWLEDGE",
            "knowledge_chunk_id": 31,
            "document_id": 7,
            "document_title": "支付标准用例库",
            "section_title": "退款异常场景",
            "page_no": 3,
            "content": "退款金额超过原订单金额时应拒绝并返回业务错误码。",
            "retrieval_score": 0.86,
        }
    ]


@pytest.mark.asyncio
async def test_collect_reference_cases_skips_absent_standard_case_knowledge() -> None:
    """项目没有标准用例知识文档时应直接返回空参考，不启动额外抽取流程。"""
    repository = SimpleNamespace(
        search_published_cases=AsyncMock(return_value=[]),
        search_standard_case_chunks=AsyncMock(return_value=[]),
    )
    service = CaseGenerationExecutionService(
        repository=repository,
        requirements_repository=SimpleNamespace(),
        ai_model_repository=AIModelRepository(SimpleNamespace()),
        prompt_template_repository=SimpleNamespace(),
        coverage_service=SimpleNamespace(),
    )

    references, signatures = await service._collect_reference_cases(
        8,
        None,
        [{"title": "登录", "description": "", "acceptance_criteria": ""}],
    )

    assert references == []
    assert signatures == []
