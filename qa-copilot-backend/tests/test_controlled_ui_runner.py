from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from app.automation.controlled_ui_runner import UIAutomationSpecDTO, run_ui_steps
from pydantic import ValidationError


@dataclass
class FakeLocator:
    selector: str
    failures: set[str]
    text: str = "登录成功"

    @property
    def first(self) -> FakeLocator:
        return self

    async def wait_for(self, *, state: str, timeout: int) -> None:
        self._check()

    async def click(self, *, timeout: int) -> None:
        self._check()

    async def fill(self, value: str, *, timeout: int) -> None:
        self._check()

    async def text_content(self, *, timeout: int) -> str | None:
        self._check()
        return self.text

    def _check(self) -> None:
        if self.selector in self.failures:
            raise TimeoutError("not found")


@dataclass
class FakePage:
    failures: set[str] = field(default_factory=set)
    url: str = "https://example.test/"

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(selector, self.failures)

    async def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        self.url = url


@pytest.mark.asyncio
async def test_ui_runner_records_reviewable_locator_fallback() -> None:
    spec = UIAutomationSpecDTO.model_validate(
        {
            "steps": [
                {"name": "打开登录页", "action": "NAVIGATE", "path": "/login"},
                {
                    "name": "点击登录",
                    "action": "CLICK",
                    "locator": "#old-login",
                    "fallbackLocators": ["button:has-text('登录')"],
                },
                {"name": "检查地址", "action": "ASSERT_URL", "value": "/login"},
            ]
        }
    )
    result = await run_ui_steps(FakePage(failures={"#old-login"}), spec, "https://example.test")
    assert result["passed"] is True
    assert result["healing_suggestions"] == [
        {
            "step_index": 2,
            "original_locator": "#old-login",
            "successful_locator": "button:has-text('登录')",
            "requires_review": True,
        }
    ]


def test_ui_protocol_rejects_external_or_traversal_navigation() -> None:
    with pytest.raises(ValidationError):
        UIAutomationSpecDTO.model_validate(
            {"steps": [{"name": "越权跳转", "action": "NAVIGATE", "path": "https://evil.example"}]}
        )
    with pytest.raises(ValidationError):
        UIAutomationSpecDTO.model_validate({"steps": [{"name": "路径穿越", "action": "NAVIGATE", "path": "/../admin"}]})
