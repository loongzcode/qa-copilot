"""固定的 HTTPX 自动化步骤解释器。"""

from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.constants import (
    AutomationAssertionType,
    AutomationExtractorSource,
    AutomationStepStatus,
)
from app.schemas.dto.automation_definitions import (
    AutomationAssertionDTO,
    AutomationDefinitionSpecDTO,
    AutomationRequestDTO,
)

VARIABLE_PATTERN = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]{0,63})\}\}")


def _render_value(value: Any, variables: dict[str, str]) -> Any:
    """递归替换 JSON 值中的变量；缺少变量时立即失败，不发送半成品请求。"""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in variables:
                raise ValueError(f"缺少运行环境变量：{key}")
            return variables[key]

        return VARIABLE_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [_render_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: _render_value(item, variables) for key, item in value.items()}
    return value


def _read_json_path(value: Any, expression: str) -> tuple[bool, Any]:
    """读取协议支持的简单 `$.a.b.0` 路径，不调用 eval 或完整脚本表达式。"""
    current = value
    for part in expression[2:].split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False, None
    return True, current


def _request_summary(request: AutomationRequestDTO, common_headers: dict[str, str]) -> dict[str, Any]:
    """只描述请求结构，不把参数值、请求头值或正文写入报告。"""
    if request.json_body is not None:
        body_type = "JSON"
        body_fields = sorted(request.json_body) if isinstance(request.json_body, dict) else []
    elif request.form_body is not None:
        body_type = "FORM"
        body_fields = sorted(request.form_body)
    else:
        body_type = "NONE"
        body_fields = []
    return {
        "queryKeys": sorted(request.query),
        "headerNames": sorted({*common_headers, *request.headers}, key=str.lower),
        "bodyType": body_type,
        "bodyFieldNames": body_fields,
    }


def _response_summary(
    *,
    status_code: int,
    content_type: str | None,
    body_size_bytes: int,
) -> dict[str, Any]:
    """保存排障需要的响应元数据，不保存响应头值或响应正文。"""
    return {
        "statusCode": status_code,
        "contentType": (content_type or "").split(";", 1)[0][:120],
        "bodySizeBytes": body_size_bytes,
    }


def _assertion_result(
    assertion: AutomationAssertionDTO,
    *,
    response: httpx.Response,
    body_text: str,
    json_body: Any,
    elapsed_ms: int,
    variables: dict[str, str],
) -> tuple[bool, dict[str, Any]]:
    """执行一条白名单断言，并只返回不会泄露实际业务值的判断摘要。"""
    passed = True
    detail: dict[str, Any] = {
        "type": assertion.type.value,
        "expression": assertion.expression,
    }
    if assertion.type == AutomationAssertionType.STATUS_CODE:
        passed = response.status_code == assertion.expected
        detail.update(expected=assertion.expected, actual=response.status_code)
    elif assertion.type == AutomationAssertionType.JSON_PATH_EXISTS:
        passed = json_body is not None and _read_json_path(json_body, assertion.expression or "")[0]
        detail.update(actual=passed)
    elif assertion.type == AutomationAssertionType.JSON_PATH_EQUALS:
        exists, actual = _read_json_path(json_body, assertion.expression or "")
        passed = exists and actual == _render_value(assertion.expected, variables)
        detail.update(actual="MATCHED" if passed else "NOT_MATCHED")
    elif assertion.type == AutomationAssertionType.HEADER_EQUALS:
        passed = response.headers.get(assertion.expression or "") == str(
            _render_value(assertion.expected, variables)
        )
        detail.update(actual="MATCHED" if passed else "NOT_MATCHED")
    elif assertion.type == AutomationAssertionType.BODY_CONTAINS:
        passed = str(_render_value(assertion.expected, variables)) in body_text
        detail.update(actual="MATCHED" if passed else "NOT_MATCHED")
    elif assertion.type == AutomationAssertionType.RESPONSE_TIME_LE:
        passed = elapsed_ms <= float(assertion.expected)
        detail.update(expected=assertion.expected, actual=elapsed_ms)
    detail["passed"] = passed
    return passed, detail


def _skipped_step(step_no: int, step: Any, common_headers: dict[str, str]) -> dict[str, Any]:
    """前一步失败后，为尚未执行的步骤生成明确的 SKIPPED 记录。"""
    return {
        "stepNo": step_no,
        "name": step.name,
        "status": AutomationStepStatus.SKIPPED.value,
        "method": step.request.method.value,
        "path": step.request.path,
        "statusCode": None,
        "durationMs": None,
        "requestSummary": _request_summary(step.request, common_headers),
        "responseSummary": {},
        "assertions": [],
        "errorMessage": "前序步骤失败，本步骤未执行",
    }


def _finish_result(
    *,
    definition: AutomationDefinitionSpecDTO,
    steps: list[dict[str, Any]],
    started_at: float,
    message: str,
) -> dict[str, Any]:
    """根据步骤状态计算任务级通过、失败、跳过数量。"""
    failed = [step for step in steps if step["status"] == AutomationStepStatus.FAILED.value]
    return {
        "success": not failed,
        "stepCount": len(definition.steps),
        "passedSteps": sum(step["status"] == AutomationStepStatus.PASSED.value for step in steps),
        "failedSteps": len(failed),
        "skippedSteps": sum(step["status"] == AutomationStepStatus.SKIPPED.value for step in steps),
        "failedStep": failed[0]["stepNo"] if failed else None,
        "message": message[:500],
        "durationMs": int((perf_counter() - started_at) * 1000),
        "steps": steps,
    }


def _finish_failure(
    *,
    definition: AutomationDefinitionSpecDTO,
    current_step_no: int,
    current_step_result: dict[str, Any],
    completed_steps: list[dict[str, Any]],
    common_headers: dict[str, str],
    started_at: float,
    message: str,
) -> dict[str, Any]:
    """加入失败步骤和后续跳过步骤，再生成完整任务结果。"""
    steps = [*completed_steps, current_step_result]
    for skipped_no, skipped in enumerate(definition.steps[current_step_no:], start=current_step_no + 1):
        steps.append(_skipped_step(skipped_no, skipped, common_headers))
    return _finish_result(
        definition=definition,
        steps=steps,
        started_at=started_at,
        message=message,
    )


def execute_controlled_http_test(runtime: dict[str, Any]) -> dict[str, Any]:
    """顺序执行受控请求并生成逐步骤脱敏报告。

    功能：根据固定 JSON 协议发送 HTTPX 请求，执行断言和变量提取，并记录
    PASSED、FAILED、SKIPPED、耗时及请求响应结构摘要。

    作用：由固定 Pytest 用例调用；返回结果由父 Worker 原子写入任务汇总表和
    步骤结果表，前端据此展示执行报告。

    为什么用它：顺序执行保证登录等前置步骤提取的变量可供后续请求使用；报告
    只保存相对路径、字段名和响应元数据，既能定位问题又不让凭据或正文落库。
    替代方案是把每步注册成独立 Pytest Item，但跨步骤变量和失败后跳过语义会
    更复杂，因此当前保留一个固定 Item、内部维护步骤结果。
    """
    started_at = perf_counter()
    definition = AutomationDefinitionSpecDTO.model_validate(runtime["definition"])
    base_url = str(runtime["baseUrl"]).rstrip("/") + "/"
    common_headers = dict(runtime.get("headers", {}))
    variables = {str(key): str(value) for key, value in runtime.get("variables", {}).items()}
    max_response_bytes = int(runtime["maxResponseBytes"])
    completed_steps: list[dict[str, Any]] = []

    with httpx.Client(follow_redirects=False, trust_env=False) as client:
        for step_no, step in enumerate(definition.steps, start=1):
            request = step.request
            step_started = perf_counter()
            step_result: dict[str, Any] = {
                "stepNo": step_no,
                "name": step.name,
                "status": AutomationStepStatus.FAILED.value,
                "method": request.method.value,
                # 保存定义中的相对路径，不保存替换变量后的实际路径。
                "path": request.path,
                "statusCode": None,
                "durationMs": None,
                "requestSummary": _request_summary(request, common_headers),
                "responseSummary": {},
                "assertions": [],
                "errorMessage": None,
            }
            try:
                path = _render_value(request.path, variables).lstrip("/")
                url = urljoin(base_url, path)
                headers = {**common_headers, **_render_value(request.headers, variables)}
                with client.stream(
                    request.method.value,
                    url,
                    headers=headers,
                    params=_render_value(request.query, variables),
                    json=_render_value(request.json_body, variables) if request.json_body is not None else None,
                    data=_render_value(request.form_body, variables) if request.form_body is not None else None,
                    timeout=httpx.Timeout(
                        float(request.timeout_seconds),
                        connect=min(10.0, float(request.timeout_seconds)),
                    ),
                ) as response:
                    body_parts: list[bytes] = []
                    body_size = 0
                    for chunk in response.iter_bytes():
                        body_size += len(chunk)
                        if body_size > max_response_bytes:
                            elapsed_ms = int((perf_counter() - step_started) * 1000)
                            step_result.update(
                                statusCode=response.status_code,
                                durationMs=elapsed_ms,
                                responseSummary=_response_summary(
                                    status_code=response.status_code,
                                    content_type=response.headers.get("content-type"),
                                    body_size_bytes=body_size,
                                ),
                                errorMessage="响应正文超过平台大小限制",
                            )
                            return _finish_failure(
                                definition=definition,
                                current_step_no=step_no,
                                current_step_result=step_result,
                                completed_steps=completed_steps,
                                common_headers=common_headers,
                                started_at=started_at,
                                message="响应正文超过平台大小限制",
                            )
                        body_parts.append(chunk)
                    body = b"".join(body_parts)

                elapsed_ms = int((perf_counter() - step_started) * 1000)
                body_text = body.decode(response.encoding or "utf-8", errors="replace")
                try:
                    json_body: Any = json.loads(body_text)
                except json.JSONDecodeError:
                    json_body = None
                step_result.update(
                    statusCode=response.status_code,
                    durationMs=elapsed_ms,
                    responseSummary=_response_summary(
                        status_code=response.status_code,
                        content_type=response.headers.get("content-type"),
                        body_size_bytes=len(body),
                    ),
                )

                for assertion in step.assertions:
                    passed, assertion_detail = _assertion_result(
                        assertion,
                        response=response,
                        body_text=body_text,
                        json_body=json_body,
                        elapsed_ms=elapsed_ms,
                        variables=variables,
                    )
                    step_result["assertions"].append(assertion_detail)
                    if not passed:
                        message = f"断言 {assertion.type.value} 未通过"
                        step_result["errorMessage"] = message
                        return _finish_failure(
                            definition=definition,
                            current_step_no=step_no,
                            current_step_result=step_result,
                            completed_steps=completed_steps,
                            common_headers=common_headers,
                            started_at=started_at,
                            message=message,
                        )

                for extractor in step.extractors:
                    if extractor.source == AutomationExtractorSource.HEADER:
                        extracted = response.headers.get(extractor.expression)
                        exists = extracted is not None
                    else:
                        exists, extracted = _read_json_path(json_body, extractor.expression)
                    if not exists:
                        message = f"变量 {extractor.name} 提取失败"
                        step_result["errorMessage"] = message
                        return _finish_failure(
                            definition=definition,
                            current_step_no=step_no,
                            current_step_result=step_result,
                            completed_steps=completed_steps,
                            common_headers=common_headers,
                            started_at=started_at,
                            message=message,
                        )
                    variables[extractor.name] = str(extracted)

                step_result["status"] = AutomationStepStatus.PASSED.value
                completed_steps.append(step_result)
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                message = f"{type(exc).__name__}: 执行步骤失败"
                step_result["durationMs"] = int((perf_counter() - step_started) * 1000)
                step_result["errorMessage"] = message
                return _finish_failure(
                    definition=definition,
                    current_step_no=step_no,
                    current_step_result=step_result,
                    completed_steps=completed_steps,
                    common_headers=common_headers,
                    started_at=started_at,
                    message=message,
                )

    return _finish_result(
        definition=definition,
        steps=completed_steps,
        started_at=started_at,
        message="全部受控接口步骤通过",
    )
