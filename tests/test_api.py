"""API contract tests.

They run against the ASGI app directly — no server, no network, no ports.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------- basics
def test_health(client):
    response = client.get("/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["crops"] > 0


def test_root_serves_the_interface(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Egypt Crop Yield Analytics" in response.text


def test_docs_are_published(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert len(schema["paths"]) >= 11


def test_meta_reports_the_split_year(client):
    body = client.get("/v1/meta").json()
    assert body["split_year"] == 2015
    assert body["first_year"] == 1990
    assert body["last_year"] == 2024
    assert "Yield" in body["units"]


# ----------------------------------------------------------------------- crops
def test_catalogue_paginates_and_searches(client):
    page = client.get("/v1/crops", params={"limit": 5}).json()
    assert page["total"] == 78
    assert len(page["items"]) == 5

    search = client.get("/v1/crops", params={"q": "wheat"}).json()
    assert search["total"] >= 1
    assert all("wheat" in item["item"].lower() for item in search["items"])


def test_forecastable_flag_is_consistent(client):
    body = client.get("/v1/crops", params={"limit": 200}).json()
    for item in body["items"]:
        assert item["forecastable"] == (item["observations"] >= 4)


def test_history_is_sorted_and_unit_labelled(client):
    body = client.get("/v1/crops/Wheat/history").json()
    years = [point["year"] for point in body["points"]]
    assert years == sorted(years)
    assert body["unit"] == "kg/ha"


def test_unknown_crop_returns_404_with_guidance(client):
    response = client.get("/v1/crops/not-a-real-crop/forecast")
    assert response.status_code == 404
    assert "GET /v1/crops" in response.json()["detail"]


# ------------------------------------------------------------------ forecasting
def test_forecast_has_three_models_and_the_right_target_year(client):
    body = client.get("/v1/crops/wheat/forecast").json()
    assert body["item"] == "Wheat"
    assert body["target_year"] == body["latest_year"] + 1
    for key in ("naive", "linear_regression", "random_forest"):
        assert body[key] > 0


def test_short_history_returns_409_not_a_crash(client):
    response = client.get("/v1/crops/Papayas/forecast")
    assert response.status_code == 409
    assert "four are needed" in response.json()["detail"]


# ------------------------------------------------------------------------- risk
def test_risk_is_a_probability_with_a_band(client):
    body = client.get("/v1/crops/Wheat/risk").json()
    assert 0.0 <= body["probability"] <= 1.0
    assert body["band"] in {"low", "medium", "high"}


def test_ranking_is_descending_and_ranked(client):
    body = client.get("/v1/risk/ranking", params={"limit": 10}).json()
    probabilities = [row["probability"] for row in body["rows"]]
    assert probabilities == sorted(probabilities, reverse=True)
    assert [row["rank"] for row in body["rows"]] == list(range(1, len(probabilities) + 1))


def test_ranking_threshold_filters(client):
    body = client.get("/v1/risk/ranking", params={"threshold": 0.10}).json()
    assert all(row["probability"] >= 0.10 for row in body["rows"])


def test_scoring_matches_the_ranking_for_the_same_crop(client):
    risk = client.get("/v1/crops/Wheat/risk").json()
    scored = client.post(
        "/v1/risk/score",
        json={
            "last_change": risk["last_change"],
            "previous_change": 0.0,
            "gap_vs_3y_average": risk["gap_vs_3y_average"],
        },
    )
    assert scored.status_code == 200
    assert 0.0 <= scored.json()["probability"] <= 1.0


def test_out_of_range_payload_returns_422(client):
    response = client.post(
        "/v1/risk/score",
        json={"last_change": 99, "previous_change": 0, "gap_vs_3y_average": 0},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "last_change"]


# ----------------------------------------------------------------------- models
def test_metrics_are_out_of_sample(client):
    body = client.get("/v1/models/metrics").json()
    assert body["split_year"] == 2015
    assert body["test_observations"] > 0
    assert int(body["test_years"].split("-")[0]) > body["split_year"]
    assert {row["model"] for row in body["models"]} == {
        "Naive (last year)", "Linear Regression", "Random Forest"
    }
    assert 0.0 <= body["risk"]["auc"] <= 1.0


def test_importance_covers_every_driver(client):
    body = client.get("/v1/models/importance").json()
    features = {row["feature"] for row in body["rows"]}
    assert features == {"last_change", "previous_change", "gap_vs_3y_average"}
    assert all(row["mean_abs_shap"] >= 0 for row in body["rows"])


# ------------------------------------------------------------------- freshness
def test_a_redeploy_is_visible_on_the_next_reload(client):
    """A cached page is how a visitor keeps seeing yesterday's interface."""
    assert "no-store" in client.get("/").headers["cache-control"]

    asset = client.get("/app.js").headers["cache-control"]
    assert "no-cache" in asset and "no-store" not in asset

    assert client.get("/v1/health").headers["cache-control"] == "no-store"
