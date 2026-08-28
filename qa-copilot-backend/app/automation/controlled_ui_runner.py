"""Playwright 受控 UI 自动化执行器。"""

from __future__ import annotations

import re
from typing import Any, Protocol, Self
from urllib.parse import urljoin, urlparse

from pydantic import Field, model_validator

from app.core.constants import UIAutomationAction
from app.exceptions import BadRequestException, ExternalServiceException
from app.schemas.camel_model import CamelModel
from app.tools.network_guard import validate_tool_hostname

_VARIABLE_PATTERN = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]{0,63})\}\}")


class UIAutomationStepDTO(CamelModel):
    """一个受控浏览器动作，不允许 JavaScript、文件上传或任意代码。"""

    name: str = Field(min_length=1, max_length=200)
    action: UIAutomationAction
    path: str | None = Field(default=None, max_length=2000)
    locator: str | None = Field(default=None, max_length=1000)
    fallback_locators: list[str] = Field(default_factory=list, max_length=5)
    value: str | None = Field(default=None, max_length=20_000)
    timeout_ms: int = Field(default=10_000, ge=100, le=60_000)

    @model_validator(mode="after")
    def validate_action_arguments(self) -> Self:
        if self.action == UIAutomationAction.NAVIGATE:
            if (
                not self.path
                or not self.path.startswith("/")
                or self.path.startswith("//")
                or ".." in self.path.split("/")
            ):
                raise ValueError("NAVIGATE 必须提供无路径穿越的站内相对 path")
        elif self.action == UIAutomationAction.ASSERT_URL:
            if not self.value:
                raise ValueError("ASSERT_URL 必须提供期望地址片段")
        elif not self.locator:
            raise ValueError(f"{self.action.value} 必须提供 locator")
        if self.action in {UIAutomationAction.FILL, UIAutomationAction.ASSERT_TEXT} and self.value is None:
            raise ValueError(f"{self.action.value} 必须提供 value")
        for locator in ([self.locator] if self.locator else []) + self.fallback_locators:
            if locator.strip().lower().startswith(("javascript:", "data:")):
                raise ValueError("定位器不能包含可执行协议")
        return self


class UIAutomationSpecDTO(CamelModel):
    """UI 执行器唯一接受的固定步骤协议。"""

    steps: list[UIAutomationStepDTO] = Field(min_length=1, max_length=100)
    variables: dict[str, str] = Field(default_factory=dict)


class LocatorLike(Protocol):
    @property
    def first(self) -> LocatorLike: ...

    async def wait_for(self, *, state: str, timeout: int) -> None: ...

    async def click(self, *, timeout: int) -> None: ...

    async def fill(self, value: str, *, timeout: int) -> None: ...

    async def text_content(self, *, timeout: int) -> str | None: ...


class PageLike(Protocol):
    @property
    def url(self) -> str: ...

    def locator(self, selector: str) -> LocatorLike: ...

    async def goto(self, url: str, *, wait_until: str, timeout: int) -> Any: ...


def _render(value: str | None, variables: dict[str, str]) -> str:
    """只替换 ``{{name}}`` 变量，不执行表达式。"""
    text = value or ""
    return _VARIABLE_PATTERN.sub(lambda match: variables.get(match.group(1), match.group(0)), text)


async def run_ui_steps(page: PageLike, spec: UIAutomationSpecDTO, base_url: str) -> dict[str, Any]:
    """顺序执行受控动作，并记录定位器降级建议和逐步结果。

    功能：执行固定动作、断言和人工候选定位器降级。
    作用：真实 Playwright 与单元测试假页面共享同一状态机。
    为什么用它：自动化步骤需要确定顺序；候选定位器只在主定位器失败后尝试并记录，
    不自动篡改正式定义，避免所谓“AI 自愈”误点相似按钮后掩盖真实回归。
    """
    results: list[dict[str, Any]] = []
    healing_suggestions: list[dict[str, Any]] = []
    for index, step in enumerate(spec.steps, start=1):
        if step.action == UIAutomationAction.NAVIGATE:
            await page.goto(
                urljoin(base_url.rstrip("/") + "/", step.path.lstrip("/")),
                wait_until="domcontentloaded",
                timeout=step.timeout_ms,
            )
            results.append({"index": index, "name": step.name, "status": "PASSED"})
            continue
        if step.action == UIAutomationAction.ASSERT_URL:
            expected = _render(step.value, spec.variables)
            if expected not in page.url:
                raise AssertionError(f"步骤 {index} 地址断言失败：当前地址不包含 {expected}")
            results.append({"index": index, "name": step.name, "status": "PASSED"})
            continue

        candidates = [step.locator, *step.fallback_locators]
        last_error: Exception | None = None
        for candidate_index, selector in enumerate(value for value in candidates if value):
            locator = page.locator(selector).first
            try:
                if step.action == UIAutomationAction.CLICK:
                    await locator.click(timeout=step.timeout_ms)
                elif step.action == UIAutomationAction.FILL:
                    await locator.fill(_render(step.value, spec.variables), timeout=step.timeout_ms)
                elif step.action == UIAutomationAction.ASSERT_VISIBLE:
                    await locator.wait_for(state="visible", timeout=step.timeout_ms)
                elif step.action == UIAutomationAction.ASSERT_TEXT:
                    actual = await locator.text_content(timeout=step.timeout_ms) or ""
                    expected = _render(step.value, spec.variables)
                    if expected not in actual:
                        raise AssertionError(f"实际文本不包含 {expected}")
                if candidate_index > 0:
                    healing_suggestions.append(
                        {
                            "step_index": index,
                            "original_locator": step.locator,
                            "successful_locator": selector,
                            "requires_review": True,
                        }
                    )
                results.append({"index": index, "name": step.name, "status": "PASSED", "locator": selector})
                break
            except Exception as exc:  # Playwright 各动作抛出不同超时/断言异常，需要尝试下一候选。
                last_error = exc
        else:
            raise AssertionError(f"步骤 {index} 执行失败：{type(last_error).__name__}") from last_error
    return {"passed": True, "steps": results, "healing_suggestions": healing_suggestions}


async def execute_playwright_ui(
    config: dict[str, Any],
    spec: UIAutomationSpecDTO,
) -> dict[str, Any]:
    """启动隔离 Chromium 浏览器，限制网络目标后执行 UI 步骤。"""
    base_url = str(config["baseUrl"]).rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BadRequestException("UI 自动化 baseUrl 必须是有效的 HTTP/HTTPS 地址")
    await validate_tool_hostname(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(accept_downloads=False)

            async def restrict_route(route: Any) -> None:
                request_host = urlparse(route.request.url).hostname
                if request_host == parsed.hostname:
                    await route.continue_()
                else:
                    await route.abort("blockedbyclient")

            await context.route("**/*", restrict_route)
            page = await context.new_page()
            result = await run_ui_steps(page, spec, base_url)
            await context.close()
            await browser.close()
            return result
    except BadRequestException, AssertionError:
        raise
    except Exception as exc:
        raise ExternalServiceException(f"Playwright UI 自动化执行失败：{type(exc).__name__}") from exc
