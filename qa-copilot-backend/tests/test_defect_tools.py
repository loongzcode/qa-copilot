from unittest.mock import AsyncMock

import httpx
import pytest
from app.exceptions import BadRequestException
from app.tools.defect_tools import DefectPlatformClient, build_defect_payload


def test_build_defect_payload_uses_an_explicit_allowlist() -> None:
    result = build_defect_payload(
        {
            "title": "登录接口返回 500",
            "description": "测试环境调用登录接口时返回服务端错误",
            "severity": "high",
            "execution_task_id": 12,
            "password": "must-not-leak",
            "unknown": "must-not-leak",
        },
        "QA",
    )

    assert result == {
        "title": "登录接口返回 500",
        "description": "测试环境调用登录接口时返回服务端错误",
        "severity": "HIGH",
        "projectKey": "QA",
        "executionTaskId": 12,
    }


def test_build_defect_payload_rejects_unknown_severity() -> None:
    with pytest.raises(BadRequestException, match="严重级别"):
        build_defect_payload({"title": "缺陷", "description": "描述", "severity": "URGENT"})


@pytest.mark.asyncio
async def test_defect_client_sends_credentials_only_as_request_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    response = httpx.Response(
        201,
        json={"key": "QA-101", "webUrl": "https://defects.example/QA-101"},
        request=httpx.Request("POST", "https://defects.example/api/issues"),
    )
    post = AsyncMock(return_value=response)
    monkeypatch.setattr("app.tools.defect_tools.validate_tool_hostname", AsyncMock())
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    client = DefectPlatformClient(
        {
            "baseUrl": "https://defects.example",
            "createPath": "/api/issues",
            "projectKey": "QA",
        },
        {"token": "secret-token"},
    )
    result = await client.create_defect({"title": "接口失败", "description": "返回 500", "severity": "CRITICAL"})

    assert result["external_id"] == "QA-101"
    request_kwargs = post.await_args.kwargs
    assert request_kwargs["headers"]["Authorization"] == "Bearer secret-token"
    assert "secret-token" not in str(request_kwargs["json"])
