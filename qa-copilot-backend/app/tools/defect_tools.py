"""缺陷平台的受控预览与创建客户端。"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.exceptions import BadRequestException, ExternalServiceException
from app.tools.network_guard import validate_tool_hostname

_ALLOWED_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def build_defect_payload(input_data: dict[str, Any], project_key: str = "") -> dict[str, Any]:
    """把工具任务输入转换为外部平台可接收的固定缺陷结构。

    功能：校验标题、描述和严重级别，并只挑选允许同步的业务字段。
    作用：预览与真实执行共用同一份映射，保证审批人看到的内容就是将要发送的内容。
    为什么用它：不能把整个 ``input_data`` 原样发送给第三方，否则内部 ID、凭据或
    未知字段可能泄露；固定白名单也便于适配 Jira、禅道或企业自建缺陷 API。
    """
    title = str(input_data.get("title", "")).strip()
    description = str(input_data.get("description", "")).strip()
    severity = str(input_data.get("severity", "MEDIUM")).strip().upper()
    if not title:
        raise BadRequestException("缺陷标题不能为空")
    if len(title) > 300:
        raise BadRequestException("缺陷标题不能超过 300 个字符")
    if not description:
        raise BadRequestException("缺陷描述不能为空")
    if len(description) > 20_000:
        raise BadRequestException("缺陷描述不能超过 20000 个字符")
    if severity not in _ALLOWED_SEVERITIES:
        raise BadRequestException("缺陷严重级别只能是 LOW、MEDIUM、HIGH 或 CRITICAL")

    payload: dict[str, Any] = {
        "title": title,
        "description": description,
        "severity": severity,
    }
    if project_key:
        payload["projectKey"] = project_key
    # 这些字段用于从 QA Copilot 追溯到原任务，不包含请求/响应正文或密钥。
    for source_name, target_name in (
        ("execution_task_id", "executionTaskId"),
        ("test_case_id", "testCaseId"),
        ("environment_name", "environmentName"),
        ("failed_step", "failedStep"),
    ):
        value = input_data.get(source_name)
        if value not in (None, ""):
            payload[target_name] = value
    return payload


class DefectPlatformClient:
    """使用受控 HTTP 请求把缺陷同步到企业缺陷平台。

    功能：校验目标地址、注入加密保存的鉴权信息并解析统一结果。
    作用：工具执行服务只负责状态机，本客户端隔离不同外部平台共有的网络细节。
    为什么用它：统一入口可以复用服务端请求伪造防护、超时和禁止重定向策略；若
    某个平台协议差异很大，可在此基础上新增适配器，而不改审批流程。
    """

    def __init__(self, config: dict[str, Any], credentials: dict[str, str]) -> None:
        self.base_url = str(config["baseUrl"]).rstrip("/") + "/"
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise BadRequestException("缺陷平台 baseUrl 必须是有效的 HTTP/HTTPS 地址")
        self.hostname = parsed.hostname
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        create_path = str(config.get("createPath", "/api/defects")).strip()
        if not create_path.startswith("/") or ".." in create_path.split("/") or "://" in create_path:
            raise BadRequestException("缺陷创建路径必须是安全的站内绝对路径")
        self.create_url = urljoin(self.base_url, create_path.lstrip("/"))
        self.project_key = str(config.get("projectKey", "")).strip()
        self.timeout = min(max(int(config.get("timeoutSeconds", 10)), 1), 30)
        self.credentials = credentials

    def _headers(self) -> dict[str, str]:
        token = self.credentials.get("token") or self.credentials.get("api_key")
        if token:
            return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        return {"Content-Type": "application/json"}

    async def create_defect(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """创建缺陷并只返回外部编号、链接和状态等非敏感结果。"""
        await validate_tool_hostname(self.hostname, self.port)
        payload = build_defect_payload(input_data, self.project_key)
        auth = None
        if self.credentials.get("username"):
            auth = (self.credentials["username"], self.credentials.get("password", ""))
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                response = await client.post(
                    self.create_url,
                    json=payload,
                    headers=self._headers(),
                    auth=auth,
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalServiceException(f"同步缺陷失败：{type(exc).__name__}") from exc
        if not isinstance(body, dict):
            raise ExternalServiceException("缺陷平台返回格式不正确")
        return {
            "external_id": body.get("id") or body.get("key") or body.get("code"),
            "external_url": body.get("url") or body.get("webUrl") or body.get("html_url"),
            "external_status": body.get("status") or "CREATED",
        }
