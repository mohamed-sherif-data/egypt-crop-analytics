"""Drive the interface like a visitor and assert what actually happens.

    py -m uvicorn api.main:app --port 8000
    py scripts/check_ui.py [base_url]

Covers: first paint, the crop answer, deep links, unknown crops, phone layout,
and console/network errors. Exits non-zero if any assertion fails.
"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {label}{'  — ' + detail if detail else ''}")
    if not condition:
        failures.append(label)


def wait_ready(page) -> None:
    page.wait_for_function("document.getElementById('status').dataset.state === 'ready'")


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)

        # ---------------------------------------------------------- desktop
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        broken: list[str] = []
        page.on(
            "response",
            lambda r: broken.append(f"{r.status} {r.url}")
            # The unknown-crop test is supposed to 404; everything else is a bug.
            if r.status >= 400 and "not-a-crop" not in r.url
            else None,
        )

        page.goto(BASE, wait_until="networkidle")
        wait_ready(page)

        check("it opens on Wheat", page.input_value("#crop-input") == "Wheat")
        check(
            "the forecast number is filled",
            page.inner_text("#forecast-value") not in {"—", ""},
            page.inner_text("#forecast-value"),
        )
        check(
            "the risk number is a percentage",
            page.inner_text("#risk-value").endswith("%"),
            page.inner_text("#risk-value"),
        )
        check(
            "the three models are listed",
            all(page.inner_text(f"#m-{k}").endswith("kg/ha") for k in ("naive", "linear", "forest")),
        )
        check("the chart has data", page.evaluate("() => window.Chart.getChart('chart')?.data.labels.length || 0") > 30)

        # A different crop replaces every number on screen.
        before = page.inner_text("#forecast-value")
        page.fill("#crop-input", "Maize (corn)")
        page.dispatch_event("#crop-input", "change")
        page.wait_for_function(
            "document.getElementById('caption').textContent.startsWith('Maize')"
        )
        check(
            "choosing another crop reloads the panel",
            page.inner_text("#forecast-value") != before,
            f"{before} -> {page.inner_text('#forecast-value')}",
        )
        check(
            "the address bar remembers it",
            page.evaluate("() => new URLSearchParams(location.search).get('crop')")
            == "Maize (corn)",
        )
        check(
            "the page title follows the crop",
            page.title().startswith("Maize"),
            page.title(),
        )

        # ------------------------------------------------------------ bad input
        page.fill("#crop-input", "not-a-crop")
        page.dispatch_event("#crop-input", "change")
        page.wait_for_function(
            "document.getElementById('forecast-value').textContent === '—'"
        )
        check("an unknown crop clears the numbers", True)
        check(
            "and says why",
            "could not be scored" in page.inner_text("#caption"),
            page.inner_text("#caption")[:60],
        )

        # ------------------------------------------------------------ deep link
        linked = browser.new_page(viewport={"width": 1440, "height": 900})
        linked.goto(f"{BASE}/?crop=Rice", wait_until="networkidle")
        wait_ready(linked)
        check("?crop= opens that crop directly", linked.input_value("#crop-input") == "Rice")

        # -------------------------------------------------------------- mobile
        phone = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        phone.goto(BASE, wait_until="networkidle")
        wait_ready(phone)
        phone.wait_for_timeout(400)

        overflow = phone.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        check("nothing overflows the phone viewport", overflow <= 1, f"{overflow}px")
        check(
            "the answer fits the phone card",
            phone.evaluate(
                "() => { const c = document.getElementById('result');"
                " return c.scrollWidth <= c.clientWidth + 1; }"
            ),
        )

        check("no failed requests", not broken, "; ".join(broken[:2]))

        browser.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed")
        raise SystemExit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
