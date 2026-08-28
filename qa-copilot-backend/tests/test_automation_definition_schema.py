"""受控自动化 JSON 协议的安全边界测试。"""

import pytest
from app.schemas.dto.automation_definitions import AutomationDefinitionSpecDTO
from pydantic import ValidationError


def valid_definition() -> dict:
    """提供包含登录取 Token 和业务请求的最小多步骤定义。"""
    return {
        "schemaVersion": "1.0",
        "steps": [
            {
                "name": "登录",
                "request": {
                    "method": "POST",
                    "path": "/api/auth/login",
                    "jsonBody": {
                        "username": "{{test_username}}",
                        "password": "{{test_password}}",
                    },
                },
                "assertions": [{"type": "STATUS_CODE", "expected": 200}],
                "extractors": [
                    {
                        "name": "access_token",
                        "source": "JSON_BODY",
                        "expression": "$.data.accessToken",
                    }
                ],
            },
            {
                "name": "查询文章",
                "request": {
                    "method": "GET",
                    "path": "/api/articles",
                    "headers": {"Authorization": "Bearer {{access_token}}"},
                },
                "assertions": [
                    {"type": "STATUS_CODE", "expected": 200},
                    {"type": "JSON_PATH_EXISTS", "expression": "$.data.records"},
                ],
            },
        ],
    }


def test_accepts_controlled_multi_step_definition() -> None:
    """合法请求、白名单断言和前序变量提取应通过校验。"""
    result = AutomationDefinitionSpecDTO.model_validate(valid_definition())
    assert len(result.steps) == 2
    assert result.steps[1].request.path == "/api/articles"


@pytest.mark.parametrize(
    "path",
    ["https://example.com/api", "//example.com/api", "/api/../../admin", "/api?a=1"],
)
def test_rejects_uncontrolled_or_ambiguous_path(path: str) -> None:
    """协议必须拒绝外部主机、路径穿越和混入 path 的查询字符串。"""
    payload = valid_definition()
    payload["steps"][0]["request"]["path"] = path
    with pytest.raises(ValidationError):
        AutomationDefinitionSpecDTO.model_validate(payload)


def test_rejects_arbitrary_code_field() -> None:
    """请求步骤中出现 python 等协议外字段时，不得静默保留。"""
    payload = valid_definition()
    payload["steps"][0]["request"]["python"] = "import os; os.system('whoami')"
    with pytest.raises(ValidationError):
        AutomationDefinitionSpecDTO.model_validate(payload)


def test_rejects_plaintext_sensitive_header() -> None:
    """认证凭据必须来自环境变量，不能把明文 Token 保存进定义。"""
    payload = valid_definition()
    payload["steps"][1]["request"]["headers"]["Authorization"] = "Bearer real-secret"
    with pytest.raises(ValidationError):
        AutomationDefinitionSpecDTO.model_validate(payload)


def test_rejects_unbalanced_variable_placeholder() -> None:
    """变量花括号不配对时必须在保存前报错。"""
    payload = valid_definition()
    payload["steps"][0]["request"]["jsonBody"]["username"] = "{{test_username}"
    with pytest.raises(ValidationError):
        AutomationDefinitionSpecDTO.model_validate(payload)
