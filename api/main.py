"""FastAPI service for the Egypt crop yield analytics.

Run locally::

    uvicorn api.main:app --reload --port 8000

Interactive documentation is served at ``/docs``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import core
from api import schemas
from api.service import FEATURE_LABELS, UNIT_BY_ELEMENT, Analytics, band

API_VERSION = "1.0.0"
WEB_DIR = Path(__file__).resolve().parents[1] / "web"

#: Loaded once per process. The CSV is small; the models are built on first use.
analytics = Analytics()

app = FastAPI(
    title="Egypt Crop Yield Analytics API",
    version=API_VERSION,
    summary="Next-year yield forecasts and decline-risk scores for 78 Egyptian crops.",
    description=(
        "Read-only service over 35 years of FAOSTAT records (Egypt, 1990-2024).\n\n"
        "**Two questions are answered for every crop**\n\n"
        "* *What is next year's yield?* Three models are compared: a naive baseline "
        "that repeats last year, a linear regression and a random forest.\n"
        "* *How likely is a drop above 10 %?* A logistic screen scores the risk and "
        "exposes the drivers behind it.\n\n"
        "**Validation** — models are fitted on years up to 2015 and judged on "
        "2016-2024, so no future information reaches training. "
        "`GET /v1/models/metrics` returns those out-of-sample scores.\n\n"
        "**Errors** — an unknown crop returns `404`; a crop with too little history "
        "for a forecast returns `409`; an invalid payload returns `422`."
    ),
    contact={"name": "Mohamed Sherif", "email": "mohamed.sherif.data@gmail.com"},
    license_info={"name": "MIT"},
    openapi_tags=[
        {"name": "meta", "description": "Service and dataset facts."},
        {"name": "crops", "description": "Catalogue and historical series."},
        {"name": "forecasting", "description": "Next-year yield forecasts."},
        {"name": "risk", "description": "Decline risk, ranking and scoring."},
        {"name": "models", "description": "Out-of-sample performance and attribution."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    """Make a redeploy visible on the next reload.

    Static hosting without Cache-Control lets browsers guess, and a guessed
    cache is how a visitor keeps seeing yesterday's interface. The page itself
    is never stored, and assets must revalidate; the API is JSON, so it is
    never stored either.
    """
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    elif path.startswith("/v1/"):
        response.headers.setdefault("Cache-Control", "no-store")
    else:
        response.headers["Cache-Control"] = "no-cache"
    return response


def _crop(item: str) -> str:
    """Resolve a crop name in any casing, or fail with a helpful 404."""
    resolved = analytics.resolve(item)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown crop '{item}'. "
                f"GET /v1/crops lists all {len(analytics.items)} valid names."
            ),
        )
    return resolved


def _crop_row(item: str) -> pd.Series:
    return analytics.catalog.loc[item]


# ------------------------------------------------------------------------ meta
@app.get("/v1/health", response_model=schemas.HealthResponse, tags=["meta"],
         summary="Liveness probe")
def health() -> schemas.HealthResponse:
    return schemas.HealthResponse(
        status="ok",
        version=API_VERSION,
        crops=len(analytics.items),
        years=f"{analytics.first_year}-{analytics.last_year}",
    )


@app.get("/v1/meta", response_model=schemas.MetaResponse, tags=["meta"],
         summary="Dataset facts and modelling convention")
def meta() -> schemas.MetaResponse:
    return schemas.MetaResponse(
        records_raw=len(analytics.raw),
        records_clean=len(analytics.data),
        crops=len(analytics.items),
        elements=analytics.elements,
        first_year=analytics.first_year,
        last_year=analytics.last_year,
        split_year=core_split_year(),
        decline_threshold=core_decline_threshold(),
        units=UNIT_BY_ELEMENT,
    )


@app.get("/v1/dataset/summary", response_model=schemas.DatasetSummary, tags=["meta"],
         summary="Cleaning report")
def dataset_summary() -> schemas.DatasetSummary:
    return schemas.DatasetSummary(**analytics.dataset_summary())


# ----------------------------------------------------------------------- crops
@app.get("/v1/crops", response_model=schemas.CropList, tags=["crops"],
         summary="Catalogue of crops with history and forecastability")
def list_crops(
    q: str | None = Query(None, description="Case-insensitive substring match"),
    forecastable_only: bool = Query(False, description="Only crops with four years of history"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.CropList:
    frame = analytics.catalog
    if q:
        frame = frame[frame.index.str.contains(q, case=False, regex=False)]
    if forecastable_only:
        frame = frame[frame["forecastable"]]

    page = frame.iloc[offset: offset + limit]
    items = [
        schemas.CropSummary(
            item=index,
            first_year=int(row["first_year"]),
            last_year=int(row["last_year"]),
            observations=int(row["observations"]),
            latest_yield=float(row["latest_yield"]),
            forecastable=bool(row["forecastable"]),
        )
        for index, row in page.iterrows()
    ]
    return schemas.CropList(total=len(frame), offset=offset, limit=limit, items=items)


@app.get("/v1/crops/{item:path}/history", response_model=schemas.HistoryResponse,
         tags=["crops"], summary="All years recorded for one crop and measurement")
def crop_history(
    item: str,
    element: schemas.ElementName = "Yield",
) -> schemas.HistoryResponse:
    name = _crop(item)
    rows = analytics.history(name, element)
    if rows.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No '{element}' records for '{name}'.",
        )
    return schemas.HistoryResponse(
        item=name,
        element=element,
        unit=UNIT_BY_ELEMENT[element],
        points=[
            schemas.HistoryPoint(year=int(year), value=float(value))
            for year, value in zip(rows["Year"], rows["Value"])
        ],
    )


# ----------------------------------------------------------------- forecasting
@app.get("/v1/crops/{item:path}/forecast", response_model=schemas.ForecastResponse,
         tags=["forecasting"], summary="Next-year yield from three models")
def crop_forecast(item: str) -> schemas.ForecastResponse:
    name = _crop(item)
    forecast = analytics.forecast_for(name)
    if forecast is None:
        row = _crop_row(name)
        raise HTTPException(
            status_code=409,
            detail=(
                f"'{name}' has {int(row['observations'])} annual observations; "
                "four are needed to build a forecast."
            ),
        )

    row = _crop_row(name)
    return schemas.ForecastResponse(
        item=name,
        target_year=int(forecast["year"]),
        latest_year=int(row["last_year"]),
        latest_yield=float(row["latest_yield"]),
        naive=float(forecast["Naive (last year)"]),
        linear_regression=float(forecast["Linear Regression"]),
        random_forest=float(forecast["Random Forest"]),
    )


# ------------------------------------------------------------------------ risk
@app.get("/v1/crops/{item:path}/risk", response_model=schemas.RiskResponse,
         tags=["risk"], summary="Drop probability for one crop")
def crop_risk(item: str) -> schemas.RiskResponse:
    name = _crop(item)
    risk = analytics.risk_for(name)
    if risk is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"'{name}' does not have the three years of history the risk "
                "screen needs."
            ),
        )
    return schemas.RiskResponse(
        item=name,
        target_year=risk["target_year"],
        probability=risk["probability"],
        band=band(risk["probability"]),
        latest_yield=risk["latest_yield"],
        last_change=risk["last_change"],
        gap_vs_3y_average=risk["gap_vs_3y_average"],
    )


@app.get("/v1/risk/ranking", response_model=schemas.RankingResponse, tags=["risk"],
         summary="Crops ranked by drop probability")
def risk_ranking(
    threshold: float = Query(0.0, ge=0.0, le=1.0, description="Minimum probability"),
    limit: int = Query(20, ge=1, le=100),
) -> schemas.RankingResponse:
    frame = analytics.ranking
    if frame.empty:
        raise HTTPException(status_code=503, detail="No crop has enough history to score.")
    frame = frame[frame["Drop probability (%)"] >= threshold * 100.0].head(limit)

    rows = [
        schemas.RankingRow(
            rank=position + 1,
            item=row["Item"],
            latest_yield=float(row["Latest yield"]),
            last_change=float(row["ch1"]),
            gap_vs_3y_average=float(row["gap"]),
            probability=float(row["Drop probability (%)"]) / 100.0,
        )
        for position, (_, row) in enumerate(frame.iterrows())
    ]
    return schemas.RankingResponse(threshold=threshold, count=len(rows), rows=rows)


@app.post("/v1/risk/score", response_model=schemas.RiskScoreResponse, tags=["risk"],
          summary="Score any scenario, not just an existing crop")
def risk_score(payload: schemas.RiskScoreRequest) -> schemas.RiskScoreResponse:
    probability = analytics.score(
        payload.last_change, payload.previous_change, payload.gap_vs_3y_average
    )
    return schemas.RiskScoreResponse(probability=probability, band=band(probability))


# ---------------------------------------------------------------------- models
@app.get("/v1/models/metrics", response_model=schemas.MetricsResponse, tags=["models"],
         summary="Out-of-sample performance of every model")
def model_metrics() -> schemas.MetricsResponse:
    metrics = analytics.metrics
    test = analytics.forecast_test
    summary = analytics.risk_summary
    lift = summary["top10_rate"] / summary["base_rate"] if summary["base_rate"] else 0.0

    return schemas.MetricsResponse(
        split_year=core_split_year(),
        test_years=f"{int(test['Year'].min())}-{int(test['Year'].max())}",
        test_observations=len(test),
        models=[
            schemas.ModelMetric(
                model=row["Model"],
                r2=float(row["R2"]),
                mae_kg_ha=float(row["MAE (kg/ha)"]),
                mape_pct=float(row["MAPE (%)"]),
            )
            for _, row in metrics.iterrows()
        ],
        risk=schemas.RiskMetrics(
            auc=float(summary["auc"]),
            base_rate=float(summary["base_rate"]) / 100.0,
            top_decile_rate=float(summary["top10_rate"]) / 100.0,
            lift=float(lift),
        ),
    )


@app.get("/v1/models/importance", response_model=schemas.ImportanceResponse,
         tags=["models"], summary="What drives the risk score")
def model_importance() -> schemas.ImportanceResponse:
    rows = []
    for _, row in analytics.importance.iterrows():
        public_name, meaning = FEATURE_LABELS[row["Feature"]]
        rows.append(
            schemas.ImportanceRow(
                feature=public_name,
                mean_abs_shap=float(row["Mean |SHAP|"]),
            )
        )
    return schemas.ImportanceResponse(
        description=(
            "Mean absolute SHAP contribution on the test period, in standardised "
            "units. For a linear model with a training-data background these values "
            "are exactly coefficient x deviation-from-training-mean. "
            + " ".join(f"{FEATURE_LABELS[key][0]}: {value[1]};" for key, value in FEATURE_LABELS.items())
        ),
        rows=rows,
    )


# --------------------------------------------------------------------- helpers
def core_split_year() -> int:
    return core.SPLIT_YEAR


def core_decline_threshold() -> float:
    return core.DECLINE_THRESHOLD


# ------------------------------------------------------------------------ web
# Mounted last so that /v1/* and /docs keep winning; serves web/index.html at "/".
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
