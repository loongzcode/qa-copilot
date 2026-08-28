from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from app.core.constants import TestEnvironmentType
from app.schemas.camel_model import CamelModel


class TestEnvironmentVariableDTO(CamelModel):
    """一个环境变量，例如 API_TOKEN 或 TEST_USERNAME。"""

    key: str = Field(min_length=1, max_length=120)
    value: str = Field(default="", max_length=10000)
    secret: bool = True

    @field_validator("key", mode="before")
    @classmethod
    def strip_key(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class TestEnvironmentBaseDTO(CamelModel):
    """新增和编辑测试环境共用的字段。"""

    name: str = Field(min_length=1, max_length=120)
    environment_type: TestEnvironmentType = TestEnvironmentType.TEST
    base_url: str = Field(min_length=1, max_length=1000)
    allowed_hosts: list[str] = Field(min_length=1, max_length=100)
    headers: dict[str, str] = Field(default_factory=dict)
    variables: list[TestEnvironmentVariableDTO] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("name", "base_url", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        """只允许明确的 HTTP(S) 地址，并禁止把账号密码直接写进 URL。"""

        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url 必须是有效的 http 或 https 地址")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url 不能包含账号或密码，请改用环境变量")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def normalize_allowed_hosts(cls, value: list[str]) -> list[str]:
        """白名单接收域名/IP；单独的 * 表示允许所有公网地址。"""

        normalized: list[str] = []
        for raw_host in value:
            host = raw_host.strip().lower().rstrip(".")
            if not host:
                raise ValueError("允许访问的域名不能为空")
            if "://" in host or "/" in host or ":" in host:
                raise ValueError("域名白名单不能包含协议、端口或路径")
            if host not in normalized:
                normalized.append(host)
        if "*" in normalized and len(normalized) > 1:
            raise ValueError("* 不能和其他域名同时配置")
        return normalized

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        """请求头名称不能为空；敏感值应写成变量占位符而不是明文。"""

        normalized: dict[str, str] = {}
        for raw_key, raw_value in value.items():
            key = raw_key.strip()
            if not key:
                raise ValueError("请求头名称不能为空")
            normalized[key] = raw_value.strip()
        return normalized

    @model_validator(mode="after")
    def validate_variable_keys(self) -> TestEnvironmentBaseDTO:
        """同一个环境中不能出现两个同名变量。"""

        keys = [variable.key for variable in self.variables]
        if len(keys) != len(set(keys)):
            raise ValueError("环境变量名称不能重复")
        base_host = urlsplit(self.base_url).hostname
        if (
            "*" not in self.allowed_hosts
            and base_host is not None
            and base_host.lower().rstrip(".") not in self.allowed_hosts
        ):
            raise ValueError("基础地址的域名必须包含在域名白名单中")
        return self


class TestEnvironmentCreateDTO(TestEnvironmentBaseDTO):
    """创建测试环境时接收的参数。"""


class TestEnvironmentUpdateDTO(CamelModel):
    """编辑测试环境；只更新请求中实际传入的字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    environment_type: TestEnvironmentType | None = None
    base_url: str | None = Field(default=None, min_length=1, max_length=1000)
    allowed_hosts: list[str] | None = Field(default=None, min_length=1, max_length=100)
    headers: dict[str, str] | None = None
    variables: list[TestEnvironmentVariableDTO] | None = None
    enabled: bool | None = None

    @field_validator("name", "base_url", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url 必须是有效的 http 或 https 地址")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url 不能包含账号或密码，请改用环境变量")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def normalize_allowed_hosts(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        for raw_host in value:
            host = raw_host.strip().lower().rstrip(".")
            if not host:
                raise ValueError("允许访问的域名不能为空")
            if "://" in host or "/" in host or ":" in host:
                raise ValueError("域名白名单不能包含协议、端口或路径")
            if host not in normalized:
                normalized.append(host)
        if "*" in normalized and len(normalized) > 1:
            raise ValueError("* 不能和其他域名同时配置")
        return normalized

    @field_validator("headers")
    @classmethod
    def validate_headers(
        cls,
        value: dict[str, str] | None,
    ) -> dict[str, str] | None:
        if value is None:
            return None
        normalized: dict[str, str] = {}
        for raw_key, raw_value in value.items():
            key = raw_key.strip()
            if not key:
                raise ValueError("请求头名称不能为空")
            normalized[key] = raw_value.strip()
        return normalized

    @model_validator(mode="after")
    def validate_variable_keys(self) -> TestEnvironmentUpdateDTO:
        if self.variables is not None:
            keys = [variable.key for variable in self.variables]
            if len(keys) != len(set(keys)):
                raise ValueError("环境变量名称不能重复")
        if self.base_url is not None and self.allowed_hosts is not None:
            base_host = urlsplit(self.base_url).hostname
            if (
                "*" not in self.allowed_hosts
                and base_host is not None
                and base_host.lower().rstrip(".") not in self.allowed_hosts
            ):
                raise ValueError("基础地址的域名必须包含在域名白名单中")
        return self
