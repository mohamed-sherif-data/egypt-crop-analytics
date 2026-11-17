"""Dataset and model access for the HTTP layer.

One :class:`Analytics` instance per process. The CSV and the feature table are
loaded at start-up (fast); the models are built on first use and then kept, so a
health check never waits for training.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

import pandas as pd

import core

DATA_FILE = Path(__file__).resolve().parents[1] / "FAOSTAT_Egypt_Agriculture_Raw.csv"

#: A crop needs this many annual yield observations before a forecast is possible.
MIN_HISTORY_YEARS = 4

UNIT_BY_ELEMENT = {"Yield": "kg/ha", "Production": "t", "Area harvested": "ha"}

#: Model feature name -> public API field name.
FEATURE_LABELS = {
    "ch1": ("last_change", "Year-on-year change in the last observed yield"),
    "ch2": ("previous_change", "Year-on-year change one year earlier"),
    "gap": ("gap_vs_3y_average", "Last yield versus its own three-year average"),
}


class Analytics:
    """Everything the API serves, derived from one CSV."""

    def __init__(self, path: Path | str = DATA_FILE) -> None:
        self.path = Path(path)
        self.raw = core.load_raw(self.path)
        self.data = core.clean(self.raw)
        self.yields = core.build_yield_table(self.data)

    # ------------------------------------------------------------- artefacts
    @cached_property
    def forecast(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        return core.train_forecasters(self.yields)

    @cached_property
    def metrics(self) -> pd.DataFrame:
        return self.forecast[0]

    @cached_property
    def forecast_test(self) -> pd.DataFrame:
        return self.forecast[1]

    @cached_property
    def risk(self) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
        return core.train_risk(self.yields)

    @cached_property
    def risk_summary(self) -> dict:
        return self.risk[0]

    @cached_property
    def importance(self) -> pd.DataFrame:
        return self.risk[2]

    @cached_property
    def ranking(self) -> pd.DataFrame:
        return core.score_next_year(self.yields)

    @cached_property
    def catalog(self) -> pd.DataFrame:
        grouped = self.yields.groupby("Item", sort=True)
        frame = pd.DataFrame(
            {
                "first_year": grouped["Year"].min(),
                "last_year": grouped["Year"].max(),
                "observations": grouped["Year"].count(),
                "latest_yield": grouped["Value"].last(),
            }
        )
        frame["forecastable"] = frame["observations"] >= MIN_HISTORY_YEARS
        return frame

    @cached_property
    def _lookup(self) -> dict[str, str]:
        return {item.lower(): item for item in self.catalog.index}

    # ---------------------------------------------------------------- facts
    @property
    def items(self) -> list[str]:
        return sorted(self.catalog.index)

    @property
    def first_year(self) -> int:
        return int(self.data["Year"].min())

    @property
    def last_year(self) -> int:
        return int(self.data["Year"].max())

    @property
    def elements(self) -> list[str]:
        return list(UNIT_BY_ELEMENT)

    def resolve(self, item: str) -> str | None:
        """Accept any casing of a crop name; return the canonical spelling."""
        return self._lookup.get(item.strip().lower())

    # -------------------------------------------------------------- queries
    def history(self, item: str, element: str) -> pd.DataFrame:
        rows = self.data[(self.data["Item"] == item) & (self.data["Element"] == element)]
        return rows.sort_values("Year")[["Year", "Value"]]

    def forecast_for(self, item: str) -> dict | None:
        return core.forecast_next(self.yields, item)

    def risk_for(self, item: str) -> dict | None:
        rows = self.ranking[self.ranking["Item"] == item]
        if rows.empty:
            return None
        row = rows.iloc[0]
        return {
            "probability": float(row["Drop probability (%)"]) / 100.0,
            "latest_yield": float(row["Latest yield"]),
            "last_change": float(row["ch1"]),
            "gap_vs_3y_average": float(row["gap"]),
            "target_year": self.last_year + 1,
        }

    def score(self, last_change: float, previous_change: float, gap: float) -> float:
        return core.score_features(self.yields, last_change, previous_change, gap)

    def dataset_summary(self) -> dict:
        duplicated = int(self.raw.duplicated(subset=["Element", "Item", "Year"]).sum())
        return {
            "records_raw": len(self.raw),
            "records_clean": len(self.data),
            "missing_values": int(self.raw["Value"].isna().sum()),
            "duplicate_keys": duplicated,
            "elements": {k: int(v) for k, v in self.data["Element"].value_counts().items()},
            "flags": {k: int(v) for k, v in self.raw["Flag"].value_counts().items()},
        }


def band(probability: float) -> str:
    """Three coarse bands, cut where the screening model is actually useful."""
    if probability >= 0.10:
        return "high"
    if probability >= 0.06:
        return "medium"
    return "low"
