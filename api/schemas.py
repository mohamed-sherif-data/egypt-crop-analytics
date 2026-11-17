"""Response and request models.

Pydantic models are the contract: they validate requests, document the API in
the generated OpenAPI schema, and keep the JSON stable for clients.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ItemName = Annotated[str, Field(examples=["Wheat"], description="Crop name, case-insensitive")]
ElementName = Annotated[
    Literal["Yield", "Production", "Area harvested"],
    Field(description="FAOSTAT measurement"),
]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    crops: int
    years: str = Field(examples=["1990-2024"])


class MetaResponse(BaseModel):
    records_raw: int
    records_clean: int
    crops: int
    elements: list[str]
    first_year: int
    last_year: int
    split_year: int = Field(description="Last year used for training")
    decline_threshold: float = Field(description="Drop size that counts as a decline")
    units: dict[str, str]


class DatasetSummary(BaseModel):
    records_raw: int
    records_clean: int
    missing_values: int
    duplicate_keys: int
    elements: dict[str, int]
    flags: dict[str, int]


class CropSummary(BaseModel):
    item: str
    first_year: int
    last_year: int
    observations: int
    latest_yield: float = Field(description="Most recent yield in kg/ha")
    forecastable: bool = Field(description="True when four years of history exist")


class CropList(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[CropSummary]


class HistoryPoint(BaseModel):
    year: int
    value: float


class HistoryResponse(BaseModel):
    item: str
    element: str
    unit: str
    points: list[HistoryPoint]


class ForecastResponse(BaseModel):
    item: str
    target_year: int
    latest_year: int
    latest_yield: float
    naive: float = Field(description="Baseline: repeats last year's yield")
    linear_regression: float
    random_forest: float
    unit: str = "kg/ha"


class RiskResponse(BaseModel):
    item: str
    target_year: int
    probability: float = Field(ge=0, le=1, description="Probability of a drop above 10 %")
    band: Literal["low", "medium", "high"]
    latest_yield: float
    last_change: float = Field(description="Year-on-year change of last observed yield")
    gap_vs_3y_average: float = Field(description="Last yield versus its three-year average")


class RankingRow(BaseModel):
    rank: int
    item: str
    latest_yield: float
    last_change: float
    gap_vs_3y_average: float
    probability: float = Field(ge=0, le=1)


class RankingResponse(BaseModel):
    threshold: float
    count: int
    rows: list[RankingRow]


class ModelMetric(BaseModel):
    model: str
    r2: float
    mae_kg_ha: float
    mape_pct: float


class RiskMetrics(BaseModel):
    auc: float
    base_rate: float
    top_decile_rate: float
    lift: float


class MetricsResponse(BaseModel):
    unit: str = "kg/ha"
    split_year: int
    test_years: str
    test_observations: int
    models: list[ModelMetric]
    risk: RiskMetrics


class ImportanceRow(BaseModel):
    feature: str
    mean_abs_shap: float


class ImportanceResponse(BaseModel):
    description: str
    rows: list[ImportanceRow]


class RiskScoreRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "examples": [{"last_change": 0.05, "previous_change": 0.02, "gap_vs_3y_average": 0.01}]
    })

    last_change: float = Field(ge=-1, le=5, description="ch1: last year over the year before, minus 1")
    previous_change: float = Field(ge=-1, le=5, description="ch2: the change one year earlier")
    gap_vs_3y_average: float = Field(ge=-1, le=10, description="gap: last year over its three-year average, minus 1")


class RiskScoreResponse(BaseModel):
    probability: float = Field(ge=0, le=1)
    band: Literal["low", "medium", "high"]
