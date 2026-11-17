"""Analytics engine for the Egypt crop yield service.

The FastAPI layer only serialises. Every numerical decision lives here so that
it can be tested without a web server and cached once per process.

Data: FAOSTAT domain "Crops and livestock products" (QCL), Egypt, 1990-2024.

Modelling convention
--------------------
A strict time split keeps every test observation out of training: models are
fitted on years up to :data:`SPLIT_YEAR` and judged on the years after it.
Two questions are asked of the same table:

* forecasting - what is next year's yield (kg/ha)?
* risk screening - how likely is a year-on-year drop above 10 %?
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

SPLIT_YEAR = 2015
DECLINE_THRESHOLD = 0.10
RANDOM_STATE = 42

YIELD = "Yield"
BASE_FEATURES = ["Year", "lag1", "lag2", "mean3"]
RISK_FEATURES = ["ch1", "ch2", "gap"]
TARGET = "drop"

FORECAST_MODELS = ["Naive (last year)", "Linear Regression", "Random Forest"]

RAW_COLUMNS = ["Element", "Item", "Year", "Value", "Flag"]

#: FAOSTAT quality flags, shortened so they fit on an axis.
FLAG_LABELS = {
    "A": "Official figure",
    "E": "Estimated value",
    "I": "Imputed by agency",
    "X": "External source",
    "M": "Missing; cannot exist",
}

# Fitting costs seconds, and the API may serve many requests per process, so
# fitted objects are memoised against a cheap signature of the training table.
_CACHE: dict[tuple[str, tuple], object] = {}


# --------------------------------------------------------------------- loading
def load_raw(path):
    """Read the FAOSTAT export and check that the columns we rely on exist."""
    raw = pd.read_csv(path)
    missing = [column for column in RAW_COLUMNS if column not in raw.columns]
    if missing:
        raise ValueError(
            f"{path} is missing required column(s): {', '.join(missing)}"
        )
    return raw


def clean(raw):
    """Keep the modelling columns, drop empty values and duplicate keys."""
    data = raw.loc[:, ["Element", "Item", "Year", "Value"]].dropna(subset=["Value"])
    data = data.drop_duplicates(subset=["Element", "Item", "Year"], keep="last")
    return data.sort_values(["Element", "Item", "Year"]).reset_index(drop=True)


def build_yield_table(data):
    """One row per crop and year for yield, with the history features attached.

    Rows are kept even when a feature is not available yet (the first three
    years of each crop); consumers that fit models drop them via
    :func:`_design`. Keeping them means the charts can still show the whole
    series.
    """
    yields = data.loc[data["Element"] == YIELD, ["Item", "Year", "Value"]].copy()
    yields = yields.sort_values(["Item", "Year"]).reset_index(drop=True)

    grouped = yields.groupby("Item", sort=False)["Value"]
    yields["lag1"] = grouped.shift(1)
    yields["lag2"] = grouped.shift(2)
    yields["lag3"] = grouped.shift(3)
    yields["mean3"] = yields[["lag1", "lag2", "lag3"]].mean(axis=1)
    return yields


# --------------------------------------------------------------------- helpers
def _signature(table):
    """Cheap identity of a table, used as a cache key."""
    return (
        len(table),
        round(float(table["Value"].sum()), 6),
        int(table["Year"].max()),
        int(table["Item"].nunique()),
    )


def _design(yields):
    """Feature matrix: own history, calendar year and crop identity."""
    feats = yields.dropna(subset=BASE_FEATURES).copy()
    matrix = pd.get_dummies(
        feats[BASE_FEATURES + ["Item"]],
        columns=["Item"],
        dtype=float,
        drop_first=True,
    )
    return feats, matrix


def _encode(rows, columns):
    """Same encoding as :func:`_design`, aligned to a fitted matrix."""
    matrix = pd.get_dummies(
        rows[BASE_FEATURES + ["Item"]],
        columns=["Item"],
        dtype=float,
        drop_first=True,
    )
    return matrix.reindex(columns=columns, fill_value=0.0)


def _standardise(scaler, matrix, fit=False):
    out = matrix.copy()
    values = matrix[BASE_FEATURES]
    out[BASE_FEATURES] = (
        scaler.fit_transform(values) if fit else scaler.transform(values)
    )
    return out


def _metrics(name, actual, predicted):
    error = np.abs(actual - predicted)
    return {
        "Model": name,
        "R2": float(r2_score(actual, predicted)),
        "MAE (kg/ha)": float(mean_absolute_error(actual, predicted)),
        "MAPE (%)": float(np.mean(error / np.abs(actual)) * 100.0),
    }


def _new_forest():
    return RandomForestRegressor(
        n_estimators=300, random_state=RANDOM_STATE, n_jobs=-1
    )


# ------------------------------------------------------------------ forecasting
def train_forecasters(yields):
    """Fit on the years up to :data:`SPLIT_YEAR`, score on the years after.

    Returns the pooled metrics table and the per-observation test predictions,
    which the dashboard re-slices per crop.
    """
    feats, matrix = _design(yields)
    if feats.empty:
        raise ValueError("No crop has enough history to build training features.")

    train_mask = feats["Year"] <= SPLIT_YEAR
    if train_mask.sum() < 20 or (~train_mask).sum() < 5:
        raise ValueError(
            f"The split year {SPLIT_YEAR} leaves too few rows to train and test on."
        )

    scaler = StandardScaler()
    train_x = _standardise(scaler, matrix[train_mask], fit=True)
    test_x = _standardise(scaler, matrix[~train_mask])
    target = feats["Value"]

    linear = LinearRegression().fit(train_x, target[train_mask])
    forest = _new_forest().fit(train_x, target[train_mask])

    test = feats.loc[~train_mask, ["Item", "Year", "Value"]].copy()
    test["Naive (last year)"] = matrix.loc[~train_mask, "lag1"].to_numpy()
    test["Linear Regression"] = linear.predict(test_x)
    test["Random Forest"] = forest.predict(test_x)

    actual = test["Value"].to_numpy()
    results = pd.DataFrame(
        [_metrics(name, actual, test[name].to_numpy()) for name in FORECAST_MODELS]
    )
    return results, test.reset_index(drop=True)


def _full_history_forecaster(yields):
    """Models refitted on every year available, used for the next-year call."""
    key = ("forecast", _signature(yields))
    if key not in _CACHE:
        feats, matrix = _design(yields)
        scaler = StandardScaler()
        train_x = _standardise(scaler, matrix, fit=True)
        _CACHE.clear()
        _CACHE[key] = {
            "columns": list(matrix.columns),
            "scaler": scaler,
            "linear": LinearRegression().fit(train_x, feats["Value"]),
            "forest": _new_forest().fit(train_x, feats["Value"]),
        }
    return _CACHE[key]


def next_year_inputs(yields, item):
    """The feature row that describes the year after the last observed one."""
    history = yields.loc[yields["Item"] == item].sort_values("Year")
    if len(history) < 4:
        return None

    last = history.iloc[-1]
    window = [last["Value"], last["lag1"], last["lag2"]]
    if any(pd.isna(value) for value in window):
        return None

    return {
        "Item": item,
        "Year": int(last["Year"]) + 1,
        "lag1": float(window[0]),
        "lag2": float(window[1]),
        "mean3": float(np.mean(window)),
    }


def forecast_next(yields, item):
    """Forecast the next year for one crop, or ``None`` if history is too short."""
    inputs = next_year_inputs(yields, item)
    if inputs is None:
        return None

    bundle = _full_history_forecaster(yields)
    matrix = _encode(pd.DataFrame([inputs]), bundle["columns"])
    matrix = _standardise(bundle["scaler"], matrix)

    return {
        "year": inputs["Year"],
        "Naive (last year)": inputs["lag1"],
        "Linear Regression": float(bundle["linear"].predict(matrix)[0]),
        "Random Forest": float(bundle["forest"].predict(matrix)[0]),
    }


# ------------------------------------------------------------------- risk model
def _risk_frame(yields):
    """History movements plus the realised outcome, for the years that have all three."""
    risk = yields.loc[
        :, ["Item", "Year", "Value", "lag1", "lag2", "lag3", "mean3"]
    ].copy()
    risk["ch1"] = risk["lag1"] / risk["lag2"] - 1.0
    risk["ch2"] = risk["lag2"] / risk["lag3"] - 1.0
    risk["gap"] = risk["lag1"] / risk["mean3"] - 1.0
    risk[TARGET] = (
        (risk["Value"] / risk["lag1"] - 1.0) < -DECLINE_THRESHOLD
    ).astype(int)
    risk = risk.replace([np.inf, -np.inf], np.nan)
    return risk.dropna(subset=RISK_FEATURES).reset_index(drop=True)


def _linear_importance(model, train_x, test_x, features):
    """Exact SHAP values for a linear model with a training-data background.

    With an independent masker, ``phi_j = beta_j * (x_j - mean_train_j)``; the
    same numbers ``shap.LinearExplainer`` returns, without the dependency.
    """
    deviation = test_x - train_x.mean(axis=0)
    shap_values = deviation * model.coef_[0]
    return (
        pd.DataFrame(
            {"Feature": features, "Mean |SHAP|": np.abs(shap_values).mean(axis=0)}
        )
        .sort_values("Mean |SHAP|")
        .reset_index(drop=True)
    )


def train_risk(yields):
    """Logistic screen for a year-on-year drop above 10 %.

    Returns the headline statistics, the test-period scores and the feature
    attribution.
    """
    risk = _risk_frame(yields)
    train_mask = risk["Year"] <= SPLIT_YEAR
    if train_mask.sum() < 20 or (~train_mask).sum() < 5:
        raise ValueError(
            f"The split year {SPLIT_YEAR} leaves too few rows to train and test on."
        )

    scaler = StandardScaler()
    train_x = scaler.fit_transform(risk.loc[train_mask, RISK_FEATURES])
    test_x = scaler.transform(risk.loc[~train_mask, RISK_FEATURES])
    train_y = risk.loc[train_mask, TARGET]
    test_y = risk.loc[~train_mask, TARGET]

    model = LogisticRegression().fit(train_x, train_y)
    probability = model.predict_proba(test_x)[:, 1]

    test = risk.loc[~train_mask, ["Item", "Year", TARGET]].copy()
    test["risk"] = probability

    base_rate = float(test_y.mean())
    headline = max(1, int(round(len(probability) * 0.10)))
    top = np.argsort(-probability)[:headline]
    summary = {
        "auc": float(roc_auc_score(test_y, probability)),
        "base_rate": base_rate * 100.0,
        "top10_rate": float(test_y.to_numpy()[top].mean()) * 100.0,
    }

    importance = _linear_importance(model, train_x, test_x, RISK_FEATURES)
    _CACHE[("risk", _signature(yields))] = (model, scaler)
    return summary, test.reset_index(drop=True), importance


def _full_history_risk(yields):
    key = ("risk", _signature(yields))
    if key not in _CACHE:
        risk = _risk_frame(yields)
        scaler = StandardScaler()
        train_x = scaler.fit_transform(risk[RISK_FEATURES])
        _CACHE[key] = (LogisticRegression().fit(train_x, risk[TARGET]), scaler)
    return _CACHE[key]


def score_next_year(yields):
    """Drop probability for every crop that has three years of history."""
    model, scaler = _full_history_risk(yields)

    rows = []
    for item, history in yields.groupby("Item", sort=True):
        history = history.sort_values("Year")
        if len(history) < 4:
            continue

        window = history["Value"].iloc[-3:].to_numpy(dtype=float)
        if np.isnan(window).any() or (window <= 0).any():
            continue

        latest, previous, earlier = window[::-1]
        rows.append(
            {
                "Item": item,
                "Latest yield": latest,
                "ch1": latest / previous - 1.0,
                "ch2": previous / earlier - 1.0,
                "gap": latest / float(window.mean()) - 1.0,
            }
        )

    columns = ["Item", "Latest yield", "ch1", "gap", "Drop probability (%)"]
    if not rows:
        return pd.DataFrame(columns=columns)

    frame = pd.DataFrame(rows)
    frame["Drop probability (%)"] = (
        model.predict_proba(scaler.transform(frame[RISK_FEATURES]))[:, 1] * 100.0
    )
    return (
        frame.loc[:, columns]
        .sort_values("Drop probability (%)", ascending=False)
        .reset_index(drop=True)
    )


def score_features(yields, ch1, ch2, gap):
    """Probability of a drop above 10 % for an arbitrary feature vector.

    Same model that scores the next year for every crop, exposed so that other
    clients can score their own scenarios through the API.
    """
    model, scaler = _full_history_risk(yields)
    features = np.array([[ch1, ch2, gap]], dtype=float)
    return float(model.predict_proba(scaler.transform(features))[0, 1])

