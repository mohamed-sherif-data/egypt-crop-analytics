"""Minimal client for the Egypt Crop Yield Analytics API.

Run against a local server (``uvicorn api.main:app``) or the deployed Space:

    py examples/api_client.py
    py examples/api_client.py https://your-space.hf.space
"""

from __future__ import annotations

import json
import sys

import httpx

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def show(title: str, payload: object) -> None:
    print(f"\n=== {title} " + "=" * max(0, 60 - len(title)))
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:1200])


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        show("health", client.get("/v1/health").json())
        show("dataset", client.get("/v1/meta").json())

        catalogue = client.get("/v1/crops", params={"q": "wheat", "limit": 5}).json()
        show("search: wheat", [item["item"] for item in catalogue["items"]])

        show("forecast: Wheat", client.get("/v1/crops/Wheat/forecast").json())
        show("risk: Wheat", client.get("/v1/crops/Wheat/risk").json())
        show("ranking", client.get("/v1/risk/ranking", params={"limit": 5}).json())

        scenario = {
            "last_change": -0.12,      # a 12 % drop last year
            "previous_change": -0.05,
            "gap_vs_3y_average": -0.08,
        }
        show("score a bad year", client.post("/v1/risk/score", json=scenario).json())

        # A deliberate error: the API explains itself rather than failing blind.
        missing = client.get("/v1/crops/nonexistent/forecast")
        print(f"\n404 check → {missing.status_code}: {missing.json()['detail']}")


if __name__ == "__main__":
    main()
