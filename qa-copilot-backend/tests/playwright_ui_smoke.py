"""本机已安装 Chromium 时运行的 Playwright 真实浏览器烟测。"""

import asyncio

from app.automation.controlled_ui_runner import UIAutomationSpecDTO, run_ui_steps
from playwright.async_api import async_playwright


async def main() -> None:
    """在内存页面中验证真实浏览器的输入、点击、文本断言和备用定位器。"""
    spec = UIAutomationSpecDTO.model_validate(
        {
            "steps": [
                {"name": "填写用户名", "action": "FILL", "locator": "#username", "value": "qa-user"},
                {
                    "name": "点击登录",
                    "action": "CLICK",
                    "locator": "#old-submit",
                    "fallbackLocators": ["button:has-text('登录')"],
                },
                {"name": "检查结果", "action": "ASSERT_TEXT", "locator": "#result", "value": "qa-user"},
            ]
        }
    )
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(
            """
            <input id="username">
            <button id="login-button">登录</button>
            <div id="result"></div>
            <script>
              document.querySelector('#login-button').onclick = () => {
                document.querySelector('#result').textContent = document.querySelector('#username').value;
              };
            </script>
            """
        )
        result = await run_ui_steps(page, spec, "https://example.test")
        await browser.close()
    if not result["passed"] or len(result["healing_suggestions"]) != 1:
        raise RuntimeError(f"Playwright smoke failed: {result}")
    print("Playwright UI smoke passed:", result)


if __name__ == "__main__":
    asyncio.run(main())
