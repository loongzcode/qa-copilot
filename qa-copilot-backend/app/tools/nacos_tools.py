"""Nacos 配置读取、脱敏比较、发布、备份和回滚工具。"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

from app.exceptions import BadRequestException, ExternalServiceException
from app.tools.network_guard import validate_tool_hostname

_SENSITIVE_KEY = re.compile(r"(password|passwd|token|secret|api[-_]?key|access[-_]?key|private[-_]?key)", re.IGNORECASE)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _parse_properties(content: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            key, separator, value = line.partition(":")
        result[key.strip()] = value.strip() if separator else ""
    return result


def parse_nacos_content(content: str, config_type: str) -> Any:
    """把 YAML、JSON、Properties 解析成可比较结构；普通文本按行比较。"""
    normalized_type = config_type.lower()
    try:
        if normalized_type in {"yaml", "yml"}:
            return yaml.safe_load(content)
        if normalized_type == "json":
            return json.loads(content)
        if normalized_type in {"properties", "property"}:
            return _parse_properties(content)
        return content.splitlines()
    except (ValueError, yaml.YAMLError) as exc:
        raise BadRequestException(f"Nacos {config_type} 配置格式不合法") from exc


def redact_sensitive(value: Any, key: str = "") -> Any:
    """递归脱敏密码、Token、Secret 等字段，比较接口永不返回明文。"""
    if _SENSITIVE_KEY.search(key):
        return "******"
    if isinstance(value, dict):
        return {str(item_key): redact_sensitive(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(child, path))
        return result
    if isinstance(value, list):
        result = {}
        for index, child in enumerate(value):
            result.update(_flatten(child, f"{prefix}[{index}]"))
        return result
    return {prefix: value}


def compare_nacos_content(source_content: str, target_content: str, config_type: str) -> dict[str, Any]:
    """比较两端配置并只返回脱敏后的新增、删除和修改项。"""
    source = _flatten(redact_sensitive(parse_nacos_content(source_content, config_type)))
    target = _flatten(redact_sensitive(parse_nacos_content(target_content, config_type)))
    changes: list[dict[str, Any]] = []
    for path in sorted(source.keys() | target.keys()):
        if path not in target:
            changes.append({"type": "ADD", "path": path, "source": source[path], "target": None})
        elif path not in source:
            changes.append({"type": "REMOVE", "path": path, "source": None, "target": target[path]})
        elif source[path] != target[path]:
            changes.append({"type": "CHANGE", "path": path, "source": source[path], "target": target[path]})
    return {
        "changes": changes,
        "source_hash": content_hash(source_content),
        "target_hash": content_hash(target_content),
        "sensitive_values_redacted": True,
        "requires_approval": bool(changes),
    }


class NacosClient:
    """Nacos OpenAPI 最小客户端，凭据只在请求内存中使用。"""

    def __init__(self, config: dict[str, Any], credentials: dict[str, str]) -> None:
        self.base_url = str(config["baseUrl"]).rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise BadRequestException("Nacos baseUrl 必须是有效的 HTTP/HTTPS 地址")
        self.hostname = parsed.hostname
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.namespace = str(config.get("namespace", ""))
        self.timeout = min(max(int(config.get("timeoutSeconds", 10)), 1), 30)
        self.credentials = credentials

    async def _token(self, client: httpx.AsyncClient) -> str | None:
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        if not username and not password:
            return self.credentials.get("accessToken")
        response = await client.post(
            f"{self.base_url}/nacos/v1/auth/login", data={"username": username, "password": password}
        )
        response.raise_for_status()
        return response.json().get("accessToken")

    async def get_config(self, data_id: str, group: str) -> str:
        try:
            await validate_tool_hostname(self.hostname, self.port)
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                token = await self._token(client)
                params = {"dataId": data_id, "group": group, "tenant": self.namespace}
                if token:
                    params["accessToken"] = token
                response = await client.get(f"{self.base_url}/nacos/v1/cs/configs", params=params)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as exc:
            raise ExternalServiceException(f"读取 Nacos 配置失败：{type(exc).__name__}") from exc

    async def publish_config(self, data_id: str, group: str, content: str, config_type: str) -> None:
        try:
            await validate_tool_hostname(self.hostname, self.port)
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                token = await self._token(client)
                data = {
                    "dataId": data_id,
                    "group": group,
                    "tenant": self.namespace,
                    "content": content,
                    "type": config_type,
                }
                if token:
                    data["accessToken"] = token
                response = await client.post(f"{self.base_url}/nacos/v1/cs/configs", data=data)
                response.raise_for_status()
                if response.text.strip().lower() != "true":
                    raise ExternalServiceException("Nacos 发布接口未返回成功")
        except httpx.HTTPError as exc:
            raise ExternalServiceException(f"发布 Nacos 配置失败：{type(exc).__name__}") from exc
