"""Capture the interface screenshots used in the docs.

Run with the service already listening:

    py -m uvicorn api.main:app --port 8000
    py scripts/screenshots.py

Devices are pinned (1440x900, dpr 1) so the images are reproducible.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[1] / "docs" / "media"
SECTIONS = ["forecast", "risk", "models", "data"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)

        page.goto(BASE, wait_until="networkidle")
        page.wait_for_function("document.getElementById('status').dataset.state === 'ready'")
        page.wait_for_timeout(900)  # let the charts finish their first animation

        page.screenshot(path=OUT / "ui-hero.png")

        # Section shots: the sticky topbar would float over the top of each
        # element capture, so hide it (and the transient status pill) first.
        page.add_style_tag(content=".topbar, .status { display: none !important; }")
        page.wait_for_timeout(120)
        for section in SECTIONS:
            page.locator(f"#{section}").screenshot(path=OUT / f"ui-{section}.png")
        page.evaluate("document.querySelectorAll('style').forEach(s => s.remove())")
        page.wait_for_timeout(120)

        # The interface (not the docs) is the deliverable, so capture the whole page.
        page.screenshot(path=OUT / "ui-full.png", full_page=True)

        browser.close()
        print(f"wrote {len(SECTIONS) + 2} images to {OUT}")


if __name__ == "__main__":
    main()
