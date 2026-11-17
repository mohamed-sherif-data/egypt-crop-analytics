# Plan v3 — Egypt Crop Yield Analytics (Streamlit removed)

> Supersedes v1 (single Streamlit app) and v2 (Streamlit as a separate client).
> The dashboard is now a plain HTML/CSS/JS client served by the API itself, so
> the project ships as **one service, one link**.

## What changed, in order

| Version | Product | Frontend | Deployment |
|---|---|---|---|
| v1 | Streamlit dashboard | Streamlit | Streamlit Cloud |
| v2 | FastAPI + Streamlit client | Streamlit (second deployment) | HF Space + Streamlit Cloud |
| **v3** | **FastAPI service** | **static `web/` SPA** | **one container, one URL** |

Two reasons Streamlit had to go:

1. **The product is an API.** A framework that renders its own interface cannot
   also expose a clean HTTP contract without adding a second runtime.
2. **One link is better than two.** A single FastAPI process serves `/v1/*`,
   `/docs` and the interface from the same origin — no CORS, no second deploy,
   no second cold start, nothing to drift.

The Streamlit code is preserved in `legacy/` for traceability, not shipped.

## Target architecture

```
                    ┌──────────────────────────┐
                    │  FAOSTAT CSV (7,978 rows)│
                    └────────────┬─────────────┘
                                 │
                       ┌─────────▼──────────┐
                       │  core.py (library) │  cleaning · features · models
                       └─────────┬──────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │  api/  FastAPI           │
                    │  /v1/*   JSON            │
                    │  /docs   Swagger UI      │
                    │  /       web/ SPA  ◄─────┼── web/index.html + styles.css + app.js
                    └────────────┬─────────────┘
                                 │  one HTTPS link
                    ┌────────────▼─────────────┐
                    │ browser · mobile · code  │
                    └──────────────────────────┘
```

## API surface (`/v1`) — unchanged and already verified

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/health` | liveness + version |
| GET | `/v1/meta` | dataset facts, split year, units |
| GET | `/v1/dataset/summary` | counts, missing values, flags |
| GET | `/v1/crops` | catalogue: search, pagination, `forecastable` |
| GET | `/v1/crops/{item}/history` | any element's series |
| GET | `/v1/crops/{item}/forecast` | next year: naive / linear / random forest |
| GET | `/v1/crops/{item}/risk` | drop probability + drivers |
| GET | `/v1/risk/ranking` | crops ranked by probability |
| GET | `/v1/models/metrics` | out-of-sample scores |
| GET | `/v1/models/importance` | feature attribution |
| POST | `/v1/risk/score` | score an arbitrary scenario |
| GET | `/docs` · `/redoc` | interactive documentation |

## Frontend scope (`web/`)

Single page, no build step, no framework:

- Hero over the supplied field photograph (`web/assets/field.webp`), dark overlay.
- Four headline figures pulled from `/v1/meta` and `/v1/models/metrics`.
- **Forecast explorer** — crop search, four stat cards, history + forecast chart (Chart.js).
- **Risk panel** — AUC / base rate / top-decile / lift, ranking table with bars,
  and a live scenario scorer wired to `POST /v1/risk/score`.
- **Models panel** — metrics table + MAPE bars + the honest note about the naive baseline.
- **Data panel** — cleaning report and FAOSTAT flag breakdown.

Design language: ink black surfaces, gold accent, emerald for growth, violet for
risk; serif display type (Instrument Serif) against Inter for the body.

## Hosting

| Option | Free | Card | Verdict |
|---|---|---|---|
| Hugging Face Space, Docker SDK | yes | no | **chosen** |
| Render free web service | yes | no | fallback (sleeps) |
| Fly.io / Cloud Run / Railway | partial | yes | rejected |

One Dockerfile, port **7860**, serves everything. Public URL shape:
`https://<user>-egypt-crop-analytics.hf.space`

## Phases

### Phase 1 — Engine  `[x]`
`core.py`, 16 tests green. Verified numbers: naive MAPE 6.37 %, AUC 0.597, lift 2.57×.

### Phase 2 — API  `[x]`
Eleven endpoints, Pydantic contracts, 404/409/422 behaviour verified with a live
ASGI client. `fastapi` raised to 0.163.2 for `starlette 1.10` compatibility.

### Phase 3 — Frontend  `[~]`
- [x] `web/index.html`, `web/styles.css`, `web/app.js`, hero image
- [ ] FastAPI mounts `web/` at `/` (routes registered first)
- [ ] Browser walkthrough of every section against the live server

### Phase 4 — Packaging  `[ ]`
- [ ] `requirements.txt` without Streamlit; `requirements-dev.txt`
- [ ] `Dockerfile` (port 7860, non-root, healthcheck)
- [ ] `README.md`, `examples/api_client.py`, WORKLOG entry

### Phase 5 — Publish  `[!]`
- [ ] Git repo + push to GitHub (login gate)
- [ ] Create and upload the HF Space (login gate)

### Phase 6 — Verify the live URL  `[ ]`
- [ ] `curl /v1/health`, `/docs`, `/` on the public host
- [ ] Screenshot the deployed interface

### Phase 7 — Handover  `[ ]`
One link, the endpoint table, what is verified, what remains weak.

## Definition of done

1. One public HTTPS URL where `/` renders the interface, `/docs` renders Swagger,
   and `/v1/health` returns `200`.
2. `pytest` green for engine and API.
3. `grep -ri streamlit` finds hits only under `legacy/`.
4. README readable in two minutes.

## Risks

| Risk | Mitigation |
|---|---|
| Chart.js / Google Fonts from CDN | Both cached by the browser; page still renders without them |
| Cold start trains models (~10 s) | Models lazy, cached per process; `/v1/health` never waits |
| Public read-only API | No writes, no keys, CORS open by design |
| HF Space sleeps when idle | Documented; first call may take ~30 s |
