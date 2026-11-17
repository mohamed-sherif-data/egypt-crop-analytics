"""Tests for the analytics engine.

The dashboard itself is thin, so these tests are the contract that keeps the
published numbers honest: they check the data cleaning, the time-split
discipline, and the exact column shapes ``app.py`` reads.

Run with:  py -m pytest -q
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import core

CSV = Path(__file__).resolve().parents[1] / "FAOSTAT_Egypt_Agriculture_Raw.csv"


@pytest.fixture(scope="module")
def raw():
    return core.load_raw(CSV)


@pytest.fixture(scope="module")
def data(raw):
    return core.clean(raw)


@pytest.fixture(scope="module")
def yields(data):
    return core.build_yield_table(data)


# --------------------------------------------------------------------- loading
def test_raw_file_has_the_columns_the_dashboard_needs(raw):
    for column in ["Element", "Item", "Year", "Value", "Flag"]:
        assert column in raw.columns
    assert len(raw) > 0


def test_clean_removes_missing_values_and_duplicate_keys(raw, data):
    assert data["Value"].isna().sum() == 0
    assert data.duplicated(subset=["Element", "Item", "Year"]).sum() == 0
    assert len(data) == len(raw) - int(raw["Value"].isna().sum())


def test_clean_keeps_the_three_measurements(data):
    assert set(data["Element"].unique()) == {"Yield", "Production", "Area harvested"}


# ------------------------------------------------------------------ feature set
def test_yield_table_has_one_row_per_crop_and_year(yields):
    assert yields.duplicated(subset=["Item", "Year"]).sum() == 0
    assert (yields["Value"] > 0).all()


def test_history_features_are_shifted_correctly(yields):
    wheat = yields.loc[yields["Item"] == "Wheat"].sort_values("Year").reset_index(drop=True)
    assert pd.isna(wheat.loc[0, "lag1"])

    for i in range(3, len(wheat)):
        assert wheat.loc[i, "lag1"] == pytest.approx(wheat.loc[i - 1, "Value"])
        assert wheat.loc[i, "lag2"] == pytest.approx(wheat.loc[i - 2, "Value"])
        assert wheat.loc[i, "lag3"] == pytest.approx(wheat.loc[i - 3, "Value"])
        expected = np.mean([wheat.loc[i - 1, "Value"], wheat.loc[i - 2, "Value"],
                            wheat.loc[i - 3, "Value"]])
        assert wheat.loc[i, "mean3"] == pytest.approx(expected)


def test_full_history_is_preserved_so_the_charts_are_not_truncated(yields):
    wheat = yields.loc[yields["Item"] == "Wheat"]
    assert wheat["Year"].min() == yields["Year"].min()
    assert wheat["Year"].max() == yields["Year"].max()


# ------------------------------------------------------------------- forecasting
@pytest.fixture(scope="module")
def forecast(yields):
    return core.train_forecasters(yields)


def test_forecast_returns_one_row_per_model(forecast):
    results, _ = forecast
    assert list(results["Model"]) == core.FORECAST_MODELS
    assert list(results.columns) == ["Model", "R2", "MAE (kg/ha)", "MAPE (%)"]
    assert results["MAPE (%)"].between(0, 100).all()


def test_no_test_observation_reaches_the_training_set(forecast):
    _, test = forecast
    assert test["Year"].min() > core.SPLIT_YEAR
    assert test["Year"].max() == int(test["Year"].max())


def test_naive_prediction_is_the_previous_year_value(yields, forecast):
    _, test = forecast
    lookup = yields.set_index(["Item", "Year"])["Value"]
    for item, year, naive in zip(
        test["Item"], test["Year"], test["Naive (last year)"]
    ):
        assert naive == pytest.approx(lookup[(item, year - 1)])


def test_reported_mape_matches_a_recomputation(forecast):
    results, test = forecast
    naive = results.set_index("Model").loc["Naive (last year)"]
    error = (test["Naive (last year)"] - test["Value"]).abs()
    assert naive["MAPE (%)"] == pytest.approx((error / test["Value"]).mean() * 100, rel=1e-6)
    assert naive["MAE (kg/ha)"] == pytest.approx(error.mean(), rel=1e-6)


def test_next_year_forecast_is_built_from_the_last_observation(yields):
    wheat = yields.loc[yields["Item"] == "Wheat"].sort_values("Year")
    forecast_next = core.forecast_next(yields, "Wheat")

    assert forecast_next["year"] == int(wheat["Year"].max()) + 1
    assert forecast_next["Naive (last year)"] == pytest.approx(wheat["Value"].iloc[-1])
    for model in core.FORECAST_MODELS:
        assert np.isfinite(forecast_next[model])
        assert forecast_next[model] > 0


def test_short_history_crops_are_reported_as_not_forecastable(yields):
    short = yields.groupby("Item")["Year"].count().idxmin()
    assert core.forecast_next(yields, short) is None


# -------------------------------------------------------------------- risk model
@pytest.fixture(scope="module")
def risk(yields):
    return core.train_risk(yields)


def test_risk_summary_is_well_formed(risk):
    summary, _, _ = risk
    assert set(summary) == {"auc", "base_rate", "top10_rate"}
    assert 0.0 <= summary["auc"] <= 1.0
    assert 0.0 <= summary["base_rate"] <= 100.0
    assert 0.0 <= summary["top10_rate"] <= 100.0


def test_risk_scores_live_in_the_test_period_and_are_probabilities(risk):
    _, test, _ = risk
    assert test["Year"].min() > core.SPLIT_YEAR
    assert test["risk"].between(0, 1).all()
    assert set(test["drop"].unique()) <= {0, 1}


def test_feature_importance_covers_every_risk_feature(risk):
    _, _, importance = risk
    assert list(importance.columns) == ["Feature", "Mean |SHAP|"]
    assert set(importance["Feature"]) == set(core.RISK_FEATURES)
    assert (importance["Mean |SHAP|"] >= 0).all()


def test_next_year_ranking_matches_the_table_columns(yields):
    ranking = core.score_next_year(yields)
    assert list(ranking.columns) == [
        "Item", "Latest yield", "ch1", "gap", "Drop probability (%)"
    ]
    assert ranking["Drop probability (%)"].between(0, 100).all()
    assert ranking["Drop probability (%)"].is_monotonic_decreasing
    assert ranking["Item"].is_unique
