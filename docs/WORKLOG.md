# Work log

Append-only record of what was done, why, and how it was verified.
Newest entry at the bottom.

---

## 2026-11-17 — Inventory

Read the four files in the project folder.

- `app.py` — 309 lines, Streamlit, five pages (Overview, Data Explorer, Yield
  Forecast, Decline Risk, Model Evaluation). It imports `core` and uses nine
  names from it.
- `core.py` — **absent**. The app therefore fails at import time.
- `FAOSTAT_Egypt_Agriculture_Raw.csv` — 7,978 rows × 15 columns, 78 crops,
  1990–2024, three measurements (Yield 2,645 / Production 2,667 / Area
  harvested 2,666), 40 missing values (0.50 %), five quality flags
  (A 5,453 · E 1,706 · I 668 · X 111 · M 40).
- `Untitled15.ipynb` — 19 cells, the exploratory prototype: `lag1/lag2/lag3`,
  `mean3`, split at 2015, Linear Regression + Random Forest against a naive
  baseline, and a logistic model for a drop above 10 % with SHAP.
- `requirements.txt` — five packages, minimum versions only, and it lacks
  `shap` even though the notebook imports it.
- No `.git`, no tests, no deployment configuration.
- Earlier screenshots in `D:\Obsidian\Automation` (`st-dash-*.png`,
  `st8504.log`) show this dashboard was already rendered locally on 2026-11-13
  on port 8504, so `core.py` existed once and was lost when the folder was
  rebuilt.

Decision: rebuild `core.py` from the contract in `app.py` + the method in the
notebook, rather than hunting for a lucky copy.

## 2026-11-17 — Engine rebuilt (`core.py`)

Public surface, exactly what `app.py` calls:

| Name | Purpose |
|---|---|
| `SPLIT_YEAR = 2015` | Last training year |
| `FLAG_LABELS` | FAOSTAT quality flags → readable labels |
| `load_raw(path)` | Read the CSV and validate the required columns |
| `clean(raw)` | Modelling columns, drop empty values and duplicate keys |
| `build_yield_table(data)` | Yield per crop-year plus `lag1`, `lag2`, `lag3`, `mean3` |
| `train_forecasters(yt)` | Metrics table + per-observation test predictions |
| `train_risk(yt)` | AUC / base rate / top-10 % rate, test scores, feature attribution |
| `forecast_next(yt, item)` | Next-year call from models refitted on all history |
| `score_next_year(yt)` | Drop probability for every crop with three years of history |

Three engineering decisions worth recording:

1. **Rows are not dropped when a lag is missing.** The notebook called `dropna`
   after shifting, which would have truncated the first three years of every
   crop in the charts. Instead the features are allowed to be `NaN` and only the
   modelling step drops them, so `Data Explorer` and the forecast history chart
   still show 1990 onwards.
2. **No `shap` dependency.** For a linear model with an independent
   (training-data) background, SHAP values are exactly
   `coef_j × (x_j − mean_train_j)`. That is the same number `shap.LinearExplainer`
   returns, without a heavy dependency at cold start. Documented in
   `core._linear_importance`.
3. **Models refitted on full history are memoised** against a cheap signature of
   the table (`len`, `Value.sum`, `max Year`, `Item.nunique`), because Streamlit
   reruns the whole script on every widget change and refitting on each rerun
   would make the page feel broken.

Bug caught during review: the first draft of `train_risk` contained a leftover
malformed expression (`risk.loc[~mask_free_columns(risk), ...] if False else ...`).
Removed before running anything.

**Verification** — `py -c` smoke run of the whole pipeline:

```
raw (7978, 15)   data (7938, 4)   yt (2645, 7)
dupes on key: 0
            Model    R2  MAE (kg/ha)  MAPE (%)
Naive (last year) 0.969      982.251     6.372
Linear Regression 0.975     1168.006    13.492
    Random Forest 0.975     1146.263     9.957
risk {'auc': 0.597, 'base_rate': 8.58, 'top10_rate': 22.059}   lift 2.57x
next wheat {'year': 2025, 'Naive': 6777.7, 'Linear': 5538.2, 'Random Forest': 6736.7}
```

Cross-check against the claims already hardcoded in `app.py`:

| Claim in the UI | Computed | Verdict |
|---|---|---|
| "the naive baseline has the lowest MAPE and MAE" | MAPE 6.37 vs 9.96 / 13.49; MAE 982 vs 1146 / 1168 | true |
| "Discrimination is weak (AUC close to 0.6)" | AUC 0.597 | true |
| "Riskiest 10 % beat random selection" | 22.1 % vs 8.6 % base rate = 2.57× | true |

So the written narrative survives contact with the recomputed numbers — no text
had to be softened.

## 2026-11-17 — `app.py` hardening

Two changes only, both justified:

1. `st.set_page_config` now sets `page_icon="🌾"` and an explicit
   `initial_sidebar_state` — the icon is what a reviewer sees in the browser tab.
2. **Crash fix in `Yield Forecast`.** `core.forecast_next` returns `None` for
   crops with fewer than four annual observations (Papayas has 2, Avocados 4).
   The old code formatted `None` with `:,.0f` and raised. The page now shows an
   informative message and still plots the observed series.
3. Footer caption naming the data source, the record count and the stack.

## 2026-11-17 — Tests

`tests/test_core.py`, 16 tests, no network and no Streamlit:

- data cleaning: no missing values, no duplicate keys, the three measurements kept
- feature engineering: lags and `mean3` recomputed for Wheat row by row,
  full history preserved
- time-split discipline: no test observation is ≤ `SPLIT_YEAR`
- naive prediction equals the previous year's value for all 677 test rows
- reported MAPE/MAE recomputed independently and matched
- next-year forecast uses the last observation; short-history crops return `None`
- risk model: probabilities in `[0, 1]`, summary keys, importance covers all three features
- next-year ranking has exactly the columns the table renders

**Verification:** `py -m pytest -q` → `16 passed in 15.96s`.

## 2026-11-17 — Pivot to v3: Streamlit removed, one service

**Instruction:** the project must be an API other clients call, and Streamlit
had to go.

**Decision:** FastAPI stops being a backend *behind* a Streamlit app and becomes
the whole product. The interface is a static `web/` bundle mounted by the same
FastAPI process at `/`, so there is one container, one origin, one URL, and no
CORS layer to maintain.

| Before | After |
|---|---|
| `app.py` (Streamlit, 20.6 kB) | `web/index.html` + `styles.css` + `app.js`, no build step |
| Two deployments | One Docker image |
| Two links, two cold starts | One link: `/`, `/docs`, `/v1/*` |

**Moves:**
- `app.py` → `legacy/streamlit_app.py`, `.streamlit/` → `legacy/streamlit-config/`.
  Kept for traceability, excluded from the image and from `requirements.txt`.
- The supplied field photograph (`New-Project-99.webp`) → `web/assets/field.webp`,
  the hero background. The other three images were moved to `docs/media/`.

**Route order matters.** `StaticFiles(html=True)` is mounted on `/` **last**.
Registered first, it would swallow `/v1/*` and `/docs`; registered last, every
explicit route wins and static files fill the gaps. Verified by calling each
path rather than by inspection.

**Dependency conflict found and fixed.** `fastapi 0.115` with `starlette 1.10`
raised `TypeError: Router.__init__() got an unexpected keyword argument
'on_startup'` at import time. `fastapi` was raised to `0.163.2`, which is the
version that matches the installed Starlette. Fixed at the requirement level,
not by pinning Starlette down.

**Interface.** Ink-black surfaces, gold as the primary accent, emerald for
growth, violet for risk. Instrument Serif for display type against Inter for
body text. Five blocks: hero, headline figures, forecast explorer, risk panel
with a live scenario scorer wired to `POST /v1/risk/score`, model metrics, data
report. The honest note — that the naive baseline beats both trained models —
is on the page itself, not buried in a README.

**Verification (HTTP, live uvicorn on 127.0.0.1:8000):**

```
/v1/health          200  {"status":"ok","version":"1.0.0","crops":78,"years":"1990-2024"}
/                   200  text/html (index)
/styles.css         200  15,723 bytes
/assets/field.webp  200  101,814 bytes
/docs               200
/openapi.json       11 paths
examples/api_client.py  ran end to end against the live server
```

**Tests:** `py -m pytest -q` → **33 passed** in 21.21 s (16 engine, 17 API).
The API tests drive the ASGI app directly, so no port and no network are needed.

## 2026-11-17 — Packaging

- `requirements.txt` — runtime only: fastapi, uvicorn, pandas, numpy,
  scikit-learn. Streamlit gone.
- `requirements-dev.txt` — `-r requirements.txt` plus pytest and httpx.
- `Dockerfile` — `python:3.12-slim`, non-root `app` user, port **7860** (what
  Hugging Face Spaces expects), healthcheck hitting `/v1/health`, and only the
  four things the service needs copied in: `core.py`, `api/`, `web/`, the CSV.
- `examples/` — Python (`httpx`), JavaScript (Node 18 `fetch`), R (`httr2`),
  each one runnable against `http://127.0.0.1:8000` or the deployed host.
- `README.md` — decision-relevant content first: what it is, the honest results
  table, quick start, endpoint table, then how it works and what is weak.

**Still open:** the public URL. Publishing needs a Hugging Face account login;
everything up to the push is finished and verified locally.
