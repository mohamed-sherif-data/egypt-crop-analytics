# Egypt Crop Yield Analytics

An HTTP API — with a browser interface on the same origin — that forecasts next
year's yield for 78 Egyptian crops and screens which ones are at risk of a
year-on-year drop.

Built on 35 years of FAOSTAT records (1990–2024). Every reported score is
measured on years the models never saw during training.

**Live service:** _added after deployment_

| | |
|---|---|
| Interface | `/` |
| Interactive API docs | `/docs` |
| OpenAPI schema | `/openapi.json` |
| Health probe | `/v1/health` |

---

## Why it is an API, not a dashboard

The requirement was a product other things can call: a mobile app, a second
dashboard, a notebook, an automated report. So the service is the product.
The page at `/` is a client — plain HTML, CSS and JavaScript with no build step
— and it uses nothing but the same public endpoints anyone else would call.
No framework, no Streamlit, no second deployment, no CORS.

---

## What it answers

| Question | Endpoint |
|---|---|
| What will next year's yield be for this crop? | `GET /v1/crops/{item}/forecast` |
| Which crops are most likely to drop more than 10 %? | `GET /v1/risk/ranking` |
| Given a scenario, what is the drop probability? | `POST /v1/risk/score` |
| What does the historical series look like? | `GET /v1/crops/{item}/history` |
| How good are the models, honestly? | `GET /v1/models/metrics` |
| What drives the risk model? | `GET /v1/models/importance` |

---

## Results (out of sample, 677 crop-year observations, 2016–2024)

| Model | R² | MAE (kg/ha) | MAPE |
|---|---|---|---|
| Naive — repeat last year | 0.969 | **982** | **6.37 %** |
| Linear regression | **0.975** | 1,168 | 13.49 % |
| Random forest | 0.975 | 1,146 | 9.96 % |

**The honest headline: the naive baseline wins on both error measures.** For
annual national yields, a crop's own last value is genuinely hard to beat, and
the two trained models do not beat it. The pooled R² is high mainly because the
models can identify which crop they are looking at — that is not the same thing
as forecasting skill, which is why MAPE and MAE lead the table.

Decline screening is real but modest:

| Metric | Value |
|---|---|
| AUC | 0.597 |
| Base rate (drops >10 %) | 8.58 % |
| Drop rate in the riskiest decile | 22.06 % |
| Lift over random selection | 2.57× |

A 0.597 AUC is weak-to-moderate. It is reported as measured, not rounded up.

---

## Quick start (local)

```bash
py -m pip install -r requirements.txt
py -m uvicorn api.main:app --reload
```

Then open <http://127.0.0.1:8000> for the interface and
<http://127.0.0.1:8000/docs> for Swagger UI.

### Call it like a client would

```bash
# next-year forecast, three models side by side
curl http://127.0.0.1:8000/v1/crops/wheat/forecast
```

```json
{
  "item": "Wheat",
  "target_year": 2025,
  "latest_year": 2024,
  "latest_yield": 6777.7,
  "naive": 6777.7,
  "linear_regression": 5538.2,
  "random_forest": 6736.7,
  "unit": "kg/ha"
}
```

```bash
# risk screening across every crop
curl "http://127.0.0.1:8000/v1/risk/ranking?limit=10"

# score an arbitrary scenario: changes as fractions, not percent
curl -X POST http://127.0.0.1:8000/v1/risk/score \
  -H "Content-Type: application/json" \
  -d '{"last_change": 0.05, "previous_change": 0.02, "gap_vs_3y_average": 0.01}'
```

Copy-paste clients in Python, JavaScript and R live in
[`examples/`](examples/).

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/health` | Liveness, version, crop count, year span |
| GET | `/v1/meta` | Dataset facts, split year, units |
| GET | `/v1/dataset/summary` | Raw/clean counts, missing values, FAOSTAT flags |
| GET | `/v1/crops` | Catalogue: `q` search, `limit`/`offset`, `forecastable` flag |
| GET | `/v1/crops/{item}/history` | Series for any crop × element |
| GET | `/v1/crops/{item}/forecast` | Next year: naive, linear, random forest |
| GET | `/v1/crops/{item}/risk` | Drop probability, band, drivers |
| GET | `/v1/risk/ranking` | Crops ranked by probability, optional `threshold` |
| POST | `/v1/risk/score` | Score a scenario |
| GET | `/v1/models/metrics` | Out-of-sample scores + risk summary |
| GET | `/v1/models/importance` | Exact SHAP values for the risk model |

Error behaviour is deliberate: unknown crop → `404` with a hint pointing at
`GET /v1/crops`; fewer than four observations → `409` explaining the minimum;
out-of-range payload → `422` naming the offending field.

---

## How it works

```
FAOSTAT CSV (7,978 rows)
        │
        ▼
    core.py ── clean · engineer features · fit models ── pure Python, no web code
        │
        ▼
    api/ ──── FastAPI · Pydantic contracts · 11 routes
        │
        ├── /v1/*   JSON for any client
        ├── /docs   Swagger UI
        └── /      web/ — static interface, same origin
```

- **Cleaning** drops rows without a yield value, normalises item names and
  provenance flags, and reports exactly what it removed (7,978 → 7,938).
- **Features** are lag-based: last year's change, the year before, and the gap
  between the current value and its own trailing three-year mean. No future
  information enters a feature, so the time split is honest.
- **Time split** at 2015: everything up to and including 2015 trains, everything
  after is scored. A random split would leak.
- **SHAP** is computed in closed form, `coef × (x − mean_train)`, which is exact
  for a linear model and avoids a heavyweight dependency.
- **Models are lazy and cached** per process, keyed on a cheap table signature,
  so `/v1/health` answers instantly even on a cold container.

---

## Tests

```bash
py -m pip install -r requirements-dev.txt
py -m pytest -q
```

**33 tests, all passing** (≈21 s):

- 16 engine tests — cleaning, feature values recomputed by hand, split
  discipline, naive prediction identity, independent recomputation of the
  reported MAPE/MAE, short-history handling, ranking shape.
- 17 API contract tests — every route, the three error codes, pagination,
  sorting, and the flag consistency between `observations` and `forecastable`.

No test touches the network or a running server; the API tests drive the ASGI
app directly.

---

## Deploy

The repository ships a single `Dockerfile` on port **7860** — the port Hugging
Face Spaces expects. It runs as a non-root user, has a healthcheck, and copies
only `core.py`, `api/`, `web/` and the CSV.

```bash
docker build -t crop-analytics .
docker run -p 7860:7860 crop-analytics
```

The same image works on any container host; see `docs/PLAN.md` for the hosting
comparison and why free-of-charge mattered here.

---

## Repository layout

```
core.py        analytics engine — cleaning, features, models, SHAP
api/           FastAPI application, service layer, Pydantic schemas
web/           interface served at / — no build step
tests/         16 engine tests + 17 API contract tests
examples/      Python, JavaScript and R clients
docs/          PLAN.md (decisions and phases), WORKLOG.md (evidence log)
legacy/        the old Streamlit app, kept for traceability, not shipped
Dockerfile     one container, port 7860
```

---

## Data

**Source:** FAOSTAT, *Crops and livestock products* (QCL), Egypt, 1990–2024.
7,978 annual records across three measurements — yield (kg/ha), production (t)
and area harvested (ha) — for 78 items. 40 missing values were removed and no
duplicate `item × year × element` keys remain.

Retrieved 2026. FAOSTAT data is free to reuse with attribution; the CSV is
included so the service is reproducible without a network call.

## Known limitations

- The naive baseline beats both trained models on MAPE and MAE. This is stated
  on the page, in this README, and in the metrics table — not hidden.
- Risk screening at AUC 0.597 is a weak signal: useful for ranking, not for
  decisions on a single crop.
- National annual averages, so the model cannot speak to within-country or
  within-season variation.
- No exogenous inputs (weather, prices, inputs) — only a crop's own history.
  Adding them is the obvious next step.
