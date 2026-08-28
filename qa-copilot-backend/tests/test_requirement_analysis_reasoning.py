"""验证需求解析使用任务级最小推理强度。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.agents import requirement_analysis_graph
from app.utils import ai_client_util


def test_chat_model_uses_task_reasoning_override(monkeypatch) -> None:
    """任务级推理强度应覆盖模型全局值，但不修改模型实体。"""

    received: dict[str, object] = {}

    def fake_chat_open_ai(**kwargs):
        received.update(kwargs)
        return object()

    monkeypatch.setattr(ai_client_util, "decrypt_secret", lambda _: "test-key")
    monkeypatch.setattr(ai_client_util, "ChatOpenAI", fake_chat_open_ai)
    provider = SimpleNamespace(
        encrypted_api_key="encrypted",
        base_url="https://example.test/v1",
        custom_headers={},
        timeout_seconds=30,
        max_retries=1,
        provider_type="openai_responses",
    )
    model = SimpleNamespace(
        model_id="reasoning-model",
        max_output_tokens=8192,
        reasoning_effort="low",
    )

    ai_client_util.create_langchain_chat_model(
        provider=provider,
        model=model,
        reasoning_effort="minimal",
    )

    assert received["reasoning_effort"] == "minimal"
    assert model.reasoning_effort == "low"


def test_requirement_node_requests_minimal_reasoning(monkeypatch) -> None:
    """需求解析节点应明确传入 minimal，防止推理耗尽全部输出额度。"""

    received: dict[str, object] = {}

    async def fake_generate_text_with_langchain(**kwargs):
        received.update(kwargs)
        return SimpleNamespace(content='{"items": []}')

    monkeypatch.setattr(
        requirement_analysis_graph,
        "generate_text_with_langchain",
        fake_generate_text_with_langchain,
    )
    prompt_template = SimpleNamespace(
        system_prompt="输出 JSON。{output_schema}",
        user_prompt="{requirement_text}\n{validation_feedback}",
    )
    model = SimpleNamespace(provider=object())
    runtime = SimpleNamespace(
        context=SimpleNamespace(
            prompt_template=prompt_template,
            ai_model_repository=object(),
            ai_model=model,
            usage_context=object(),
        )
    )

    result = asyncio.run(
        requirement_analysis_graph.extract_requirement_items(
            {
                "requirement_text": "发布文章需求",
                "validation_feedback": "",
            },
            runtime,
        )
    )

    assert received["reasoning_effort"] == "minimal"
    assert result["raw_output"] == '{"items": []}'
