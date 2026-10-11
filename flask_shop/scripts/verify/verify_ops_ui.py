# -*- coding: utf-8 -*-
"""Headless smoke test for the merchant operations assistant."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:8081/admin"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
LOGIN_BUTTON = "\u8fdb\u5165\u5de5\u4f5c\u53f0"
OVERVIEW_BUTTON = "\u4e00\u952e\u7ecf\u8425\u901f\u89c8"
OVERVIEW_TEXT = "\u8fd0\u8425\u901f\u89c8"


def main() -> int:
    screenshot = Path(tempfile.gettempdir()) / "ops-assistant-smoke.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    console_errors: list[dict] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROME_PATH, headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on(
            "console",
            lambda message: console_errors.append(
                {"text": message.text, "url": message.location.get("url", "")}
            )
            if message.type == "error"
            else None,
        )

        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        inputs = page.locator("input")
        inputs.nth(0).fill("demo")
        inputs.nth(1).fill("admin")
        inputs.nth(2).fill("123456")
        page.get_by_role("button", name=LOGIN_BUTTON).click()
        page.wait_for_url("**/data_list", timeout=10_000)

        page.goto(f"{BASE_URL}/agent_ops", wait_until="networkidle")
        page.get_by_role("button", name=OVERVIEW_BUTTON).click()
        page.wait_for_function(
            "document.querySelectorAll('.row.assistant').length >= 2",
            timeout=10_000,
        )

        reply = page.locator(".row.assistant .text").last.inner_text()
        agents = page.locator(".row.assistant .agents").last.inner_text()
        page.screenshot(path=str(screenshot), full_page=True)
        browser.close()

    result = {
        "ok": OVERVIEW_TEXT in reply and "ops" in agents and not console_errors,
        "reply": reply,
        "agents": agents,
        "console_errors": console_errors,
        "screenshot": str(screenshot),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
