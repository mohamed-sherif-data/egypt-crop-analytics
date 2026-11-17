# Plan v4 — Egypt Crop Yield Analytics (deployed)

> Supersedes v1 (single Streamlit app), v2 (Streamlit as a separate client) and
> v3 (Streamlit removed, hosting still assumed to be a Hugging Face Space).
> The product is a FastAPI service whose interface it serves itself, so the
> project ships as **one service, one link**.

**Live:** <https://mohamed-sherif-data--crop-api.modal.run>
**Code:** <https://github.com/mohamed-sherif-data/egypt-crop-analytics>

## What changed, in order

| Version | Product | Frontend | Deployment |
|---|---|---|---|
| v1 | Streamlit dashboard | Streamlit | Streamlit Cloud |
| v2 | FastAPI + Streamlit client | Streamlit (second deployment) | HF Space + Streamlit Cloud |
| v3 | FastAPI service | static `web/` SPA | one container, one URL |
| **v4** | **same service** | **same SPA** | **Modal, serverless ASGI** |

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

The assumption in v3 — that a free Hugging Face Docker Space would host this —
turned out to be wrong on the day of deployment. The hosting was decided by
attempting each candidate, not by reading marketing pages:

| Option | Free? | Card? | Outcome |
|---|---|---|---|
| Hugging Face Space, Docker SDK | no | — | **rejected**: the API answers `402 Payment Required`; free `cpu-basic` is limited to Static Spaces, Docker and Gradio need PRO |
| Render free web service | no | yes | **rejected**: the deploy button opens "Add Card" even with the $0 instance type selected |
| Koyeb | yes | no | **rejected**: email verification passed, console then returned `401` on every API call and redirected to an empty settings page |
| **Modal, serverless ASGI** | **yes** | **no** | **chosen**: $1/month free compute without a card, GitHub auth, `modal deploy` from this repo |
| Fly.io / Cloud Run / Railway | partial | yes | rejected |

Public URL:

```
https://mohamed-sherif-data--crop-api.modal.run
```

The container definition is still the portable artefact: the same `Dockerfile`
runs on any host that takes a port. Modal mounts the same files and serves the
same ASGI object, so behaviour is identical.

## Phases

### Phase 1 — Engine  `[x]`
`core.py`, 16 tests green. Verified numbers: naive MAPE 6.37 %, AUC 0.597, lift 2.57×.

### Phase 2 — API  `[x]`
Eleven endpoints, Pydantic contracts, 404/409/422 behaviour verified with a live
ASGI client. `fastapi` raised to 0.163.2 for `starlette 1.10` compatibility.

### Phase 3 — Frontend  `[x]`
- [x] `web/index.html`, `web/styles.css`, `web/app.js`, hero image
- [x] FastAPI mounts `web/` at `/` (routes registered first; mount last)
- [x] Browser walkthrough of every section against the live server
- [x] Screenshots captured by script at a pinned viewport (1440×900, dpr 1)
- [x] Unknown-crop path clears the stale numbers instead of leaving another
      crop's values on screen

### Phase 4 — Packaging  `[x]`
- [x] `requirements.txt` without Streamlit; `requirements-dev.txt`
- [x] `Dockerfile` (`$PORT` or 7860, non-root, healthcheck)
- [x] `README.md`, `examples/` in Python, JavaScript and R
- [x] Git repository, first commit, public GitHub repo

### Phase 5 — Publish  `[x]`
- [x] Git repo pushed: <https://github.com/mohamed-sherif-data/egypt-crop-analytics>
- [x] Service deployed to Modal: <https://mohamed-sherif-data--crop-api.modal.run>

### Phase 6 — Verify the live URL  `[x]`
- [x] `curl /v1/health` → 200 with the crop count and year span
- [x] `/` → 200 `text/html`, `/styles.css` and the hero image → 200
- [x] `/docs` → 200, openapi.json lists 11 paths
- [x] `/v1/crops/wheat/forecast` → the three models, target year 2025
- [x] `404` for an unknown crop, `409` for a crop with too little history
- [x] Interface rendered in a real browser against the live host: KPIs, 12
      ranking rows, chart, scenario scorer

### Phase 7 — Handover  `[x]`
One link, the endpoint table, what is verified, what remains weak.

## Definition of done

1. One public HTTPS URL where `/` renders the interface, `/docs` renders Swagger,
   and `/v1/health` returns `200`. **Verified.**
2. `pytest` green for engine and API. **33 passed.**
3. No Streamlit dependency, import or executable reference outside `legacy/`;
   the docs mention it only as history. **Verified.**
4. README readable in two minutes, with the real link. **Verified.**

## Risks

| Risk | Mitigation |
|---|---|
| Chart.js / Google Fonts from CDN | Both cached by the browser; page still renders without them |
| Cold start trains models (~10 s) | Models lazy, cached per process; `/v1/health` never waits |
| Public read-only API | No writes, no keys, CORS open by design |
| Serverless host scales to zero | Documented in the README; first request after idle warms up |
| Free compute is $1/month on this host | The app costs cents per session; the container is capped at one replica |
