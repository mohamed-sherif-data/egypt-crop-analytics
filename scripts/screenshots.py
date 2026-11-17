"""Capture the interface screenshots used in the docs.

Run with the service already listening:

    py -m uvicorn api.main:app --port 8000
    py scripts/screenshots.py [base_url] [subfolder]

Devices are pinned (1440x900 and 390x844, dpr 1) so images are reproducible.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
SUBDIR = sys.argv[2] if len(sys.argv) > 2 else ""
OUT = Path(__file__).resolve().parents[1] / "docs" / "media" / SUBDIR


def settle(page) -> None:
    page.wait_for_function("document.getElementById('status').dataset.state === 'ready'")
    page.wait_for_timeout(900)  # let the chart finish its first animation


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)

        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(BASE, wait_until="networkidle")
        settle(page)
        page.screenshot(path=OUT / "ui-hero.png")

        # The answer card is the product; capture it without the floating chrome.
        page.add_style_tag(content=".topbar, .status { display: none !important; }")
        page.wait_for_timeout(120)
        page.locator("#result").screenshot(path=OUT / "ui-result.png")
        page.evaluate("document.querySelectorAll('style').forEach(s => s.remove())")

        page.screenshot(path=OUT / "ui-full.png", full_page=True)

        phone = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, has_touch=True
        )
        phone.goto(BASE, wait_until="networkidle")
        settle(phone)
        phone.screenshot(path=OUT / "ui-phone.png", full_page=True)

        browser.close()
        print(f"wrote 4 images to {OUT}")


if __name__ == "__main__":
    main()
