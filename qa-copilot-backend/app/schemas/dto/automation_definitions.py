"""自动化定义接口接收模型及受控 JSON 安全校验。"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.core.constants import (
    AutomationAssertionType,
    AutomationExtractorSource,
    AutomationHttpMethod,
)
from app.schemas.camel_model import CamelModel

VARIABLE_PATTERN = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]{0,63})\}\}")
SENSITIVE_HEADERS = {"authorization", "cookie", "proxy-authorization", "x-api-key", "x-auth-token"}
FORBIDDEN_HEADERS = {"host", "content-length", "connection", "transfer-encoding"}
MAX_DEFINITION_BYTES = 200_000
MAX_JSON_DEPTH = 20
MAX_JSON_NODES = 5_000


def _validate_controlled_value(value: Any) -> None:
    """递归检查请求数据只能包含安全 JSON 值和受控变量占位符。

    功能：限制嵌套深度、节点数量、危险键和未配对的花括号。
    作用：所有请求头、查询参数和请求正文共用同一条安全边界。
    为什么用它：只依靠顶层 Pydantic 字段无法检查任意深度 JSON；递归遍历比
    执行或解析用户脚本安全。替代方案是 JSON Schema，后续跨语言时可导出使用。
    """

    node_count = 0

    def visit(current: Any, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > MAX_JSON_NODES:
            raise ValueError("自动化定义的 JSON 节点数量不能超过 5000")
        if depth > MAX_JSON_DEPTH:
            raise ValueError("自动化定义的 JSON 嵌套层级不能超过 20")
        if current is None or isinstance(current, bool | int):
            return
        if isinstance(current, float):
            if not math.isfinite(current):
                raise ValueError("JSON 数字不能是 NaN 或无穷大")
            return
        if isinstance(current, str):
            stripped = VARIABLE_PATTERN.sub("", current)
            if "{{" in stripped or "}}" in stripped:
                raise ValueError("变量只能使用 {{variable_name}} 格式")
            return
        if isinstance(current, list):
            for item in current:
                visit(item, depth + 1)
            return
        if isinstance(current, dict):
            for key, item in current.items():
                if not isinstance(key, str) or not key:
                    raise ValueError("JSON 对象的键必须是非空字符串")
                if key.startswith("__"):
                    raise ValueError("JSON 键不能以双下划线开头")
                if "{{" in key or "}}" in key or any(ord(char) < 32 for char in key):
                    raise ValueError("JSON 对象的键不能包含变量或控制字符")
                visit(item, depth + 1)
            return
        raise ValueError("自动化定义只允许 JSON 基础类型")

    visit(value, 0)


class AutomationRequestDTO(CamelModel):
    """一个受控的 HTTP 请求步骤，不包含主机地址或可执行代码。"""

    model_config = CamelModel.model_config | {"extra": "forbid"}

    method: AutomationHttpMethod
    path: str = Field(min_length=1, max_length=2000)
    headers: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    json_body: Any | None = None
    form_body: dict[str, Any] | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=60)

    @field_validator("path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        """只允许由测试环境补全域名的站内相对路径。"""
        path = value.strip()
        lowered = path.lower()
        if (
            not path.startswith("/")
            or path.startswith("//")
            or "://" in lowered
            or "\\" in path
            or ".." in path.split("/")
            or "?" in path
            or any(ord(char) < 32 for char in path)
        ):
            raise ValueError("path 必须是无查询字符串、无 .. 的站内相对路径")
        _validate_controlled_value(path)
        return path

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, headers: dict[str, Any]) -> dict[str, Any]:
        """拒绝协议控制头，并要求敏感凭据通过运行环境变量注入。"""
        normalized = {name.lower(): value for name, value in headers.items()}
        forbidden = FORBIDDEN_HEADERS.intersection(normalized)
        if forbidden:
            raise ValueError(f"不允许设置协议控制请求头：{', '.join(sorted(forbidden))}")
        for name in SENSITIVE_HEADERS.intersection(normalized):
            value = normalized[name]
            if not isinstance(value, str) or VARIABLE_PATTERN.search(value) is None:
                raise ValueError(f"敏感请求头 {name} 必须使用环境变量占位符")
        _validate_controlled_value(headers)
        return headers

    @field_validator("query", "json_body", "form_body")
    @classmethod
    def validate_request_data(cls, value: Any) -> Any:
        _validate_controlled_value(value)
        return value

    @model_validator(mode="after")
    def validate_single_body(self) -> AutomationRequestDTO:
        """同一请求只能选择 JSON 正文或表单正文，避免编码语义冲突。"""
        if self.json_body is not None and self.form_body is not None:
            raise ValueError("jsonBody 与 formBody 不能同时存在")
        return self


class AutomationAssertionDTO(CamelModel):
    """白名单断言；不同类型只允许使用各自需要的参数。"""

    model_config = CamelModel.model_config | {"extra": "forbid"}

    type: AutomationAssertionType
    expression: str | None = Field(default=None, min_length=1, max_length=500)
    expected: Any | None = None

    @model_validator(mode="after")
    def validate_arguments(self) -> AutomationAssertionDTO:
        """校验每种断言的必需参数，防止执行器运行时才发现定义不完整。"""
        expression_required = {
            AutomationAssertionType.JSON_PATH_EQUALS,
            AutomationAssertionType.JSON_PATH_EXISTS,
            AutomationAssertionType.HEADER_EQUALS,
        }
        expected_required = {
            AutomationAssertionType.STATUS_CODE,
            AutomationAssertionType.JSON_PATH_EQUALS,
            AutomationAssertionType.HEADER_EQUALS,
            AutomationAssertionType.BODY_CONTAINS,
            AutomationAssertionType.RESPONSE_TIME_LE,
        }
        if self.type in expression_required and not self.expression:
            raise ValueError(f"{self.type.value} 断言必须提供 expression")
        if self.type in expected_required and self.expected is None:
            raise ValueError(f"{self.type.value} 断言必须提供 expected")
        if self.type == AutomationAssertionType.STATUS_CODE and (
            not isinstance(self.expected, int) or not 100 <= self.expected <= 599
        ):
            raise ValueError("STATUS_CODE.expected 必须是 100 到 599 的整数")
        if self.type == AutomationAssertionType.RESPONSE_TIME_LE and (
            not isinstance(self.expected, int | float)
            or isinstance(self.expected, bool)
            or self.expected <= 0
            or self.expected > 60_000
        ):
            raise ValueError("RESPONSE_TIME_LE.expected 必须是 1 到 60000 的毫秒数")
        if self.type in {
            AutomationAssertionType.JSON_PATH_EQUALS,
            AutomationAssertionType.JSON_PATH_EXISTS,
        } and self.expression and not self.expression.startswith("$."):
            raise ValueError("JSON 路径必须从 $. 开始")
        _validate_controlled_value(self.expected)
        return self


class AutomationExtractorDTO(CamelModel):
    """从某一步响应中提取变量，供后续步骤通过占位符引用。"""

    model_config = CamelModel.model_config | {"extra": "forbid"}

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    source: AutomationExtractorSource
    expression: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_expression(self) -> AutomationExtractorDTO:
        if self.source == AutomationExtractorSource.JSON_BODY and not self.expression.startswith("$."):
            raise ValueError("JSON_BODY 提取表达式必须从 $. 开始")
        if self.source == AutomationExtractorSource.HEADER and any(
            char in self.expression for char in "\r\n:"
        ):
            raise ValueError("HEADER 提取表达式必须是单个响应头名称")
        return self


class AutomationStepDTO(CamelModel):
    """自动化定义中的一个顺序执行步骤。"""

    model_config = CamelModel.model_config | {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=300)
    request: AutomationRequestDTO
    assertions: list[AutomationAssertionDTO] = Field(min_length=1, max_length=50)
    extractors: list[AutomationExtractorDTO] = Field(default_factory=list, max_length=20)


class AutomationDefinitionSpecDTO(CamelModel):
    """执行器唯一接受的自动化测试定义协议。"""

    model_config = CamelModel.model_config | {"extra": "forbid"}

    schema_version: Literal["1.0"] = "1.0"
    steps: list[AutomationStepDTO] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_size_and_variables(self) -> AutomationDefinitionSpecDTO:
        """限制定义体积，并阻止不同步骤重复定义同名提取变量。"""
        dumped = self.model_dump(mode="json", by_alias=True)
        if len(json.dumps(dumped, ensure_ascii=False).encode("utf-8")) > MAX_DEFINITION_BYTES:
            raise ValueError("自动化定义不能超过 200 KB")

        extracted_variables: set[str] = set()
        for step in self.steps:
            for extractor in step.extractors:
                if extractor.name in extracted_variables:
                    raise ValueError(f"提取变量 {extractor.name} 不能重复定义")
                extracted_variables.add(extractor.name)
        # 请求中可以引用测试环境里的密钥变量；环境选择发生在运行阶段，因此这里
        # 只验证 {{variable_name}} 语法，不提前要求变量一定来自前序提取器。
        return self


class AutomationDefinitionUpdateDTO(CamelModel):
    """编辑草稿定义时接收名称和完整受控 JSON。"""

    name: str = Field(min_length=1, max_length=300)
    definition: AutomationDefinitionSpecDTO

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value
