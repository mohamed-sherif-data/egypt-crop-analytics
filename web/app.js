/* ============================================================================
   Egypt Crop Yield Analytics — client
   Talks only to the public API (same origin). No framework, no build step.
   ========================================================================== */

const API = "";                      // same origin when served by FastAPI
const $ = (id) => document.getElementById(id);
const num = new Intl.NumberFormat("en-US");
const one = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const two = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const COLORS = {
  gold: "#d4af37",
  goldSoft: "#e7cc7a",
  green: "#2fa37a",
  purple: "#8b6be0",
  grey: "#6b7885",
  text: "#eceef1",
  grid: "#1b222a",
  tick: "#8b98a5",
};

let forecastChart = null;
let currentCrop = null;
let baseRate = 0.0858;        // replaced with the measured test-period rate on boot
const GAUGE_MAX = 0.25;       // the gauge saturates at 25 % so small moves stay visible

/* ------------------------------------------------------------------ helpers */
async function get(path) {
  const response = await fetch(API + path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body && body.detail) detail = typeof body.detail === "string" ? body.detail : detail;
    } catch { /* keep the status text */ }
    throw new Error(detail);
  }
  return response.json();
}

async function post(path, payload) {
  const response = await fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function status(state, text) {
  const bar = $("status");
  bar.dataset.state = state;
  $("status-text").textContent = text;
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

function chartDefaults() {
  if (!window.Chart) return;
  Chart.defaults.color = COLORS.tick;
  Chart.defaults.font.family = 'Inter, "Segoe UI", system-ui, sans-serif';
  Chart.defaults.font.size = 11;
  Chart.defaults.borderColor = COLORS.grid;
}

/* --------------------------------------------------------------- bootstrap */
async function boot() {
  chartDefaults();

  try {
    const [health, meta, metrics, summary, ranking] = await Promise.all([
      get("/v1/health"),
      get("/v1/meta"),
      get("/v1/models/metrics"),
      get("/v1/dataset/summary"),
      get("/v1/risk/ranking?limit=12"),
    ]);

    renderHeadline(meta, metrics);
    renderDataset(meta, summary);
    renderRisk(metrics, ranking);
    renderMetrics(metrics);

    await loadCropList();
    status("ready", "Ready");
  } catch (error) {
    status("error", `Could not reach the API — ${error.message}`);
    console.error(error);
  }

  wireScorer();
}

function renderHeadline(meta, metrics) {
  $("kpi-records").textContent = num.format(meta.records_raw);
  $("kpi-crops").textContent = num.format(meta.crops);
  $("kpi-years").textContent = `${meta.first_year}–${meta.last_year}`;
  $("hero-crops").textContent = num.format(meta.crops);

  const best = metrics.models.reduce((a, b) => (a.mape_pct <= b.mape_pct ? a : b));
  $("kpi-mape").textContent = `${two.format(best.mape_pct)}%`;
  $("kpi-mape-model").textContent = best.model;
}

function renderDataset(meta, summary) {
  $("data-raw").textContent = num.format(summary.records_raw);
  $("data-clean").textContent = num.format(summary.records_clean);
  $("data-dupes").textContent = num.format(summary.duplicate_keys);
  $("data-elements").textContent = num.format(Object.keys(summary.elements).length);
  $("data-missing-chip").textContent = `${num.format(summary.missing_values)} missing values removed`;

  $("models-caption").textContent =
    `Trained on years up to ${meta.split_year}, judged on ${meta.first_year + 0 === 0 ? "" : ""}the years after it.`;

  const total = Object.values(summary.flags).reduce((a, b) => a + b, 0) || 1;
  const labels = {
    A: "Official figure",
    E: "Estimated value",
    I: "Imputed by agency",
    X: "External source",
    M: "Missing; cannot exist",
  };

  $("flags").innerHTML = Object.entries(summary.flags)
    .sort((a, b) => b[1] - a[1])
    .map(([code, count]) => {
      const share = (count / total) * 100;
      return `<li>
        <span>${labels[code] || code}</span>
        <span class="bar"><span style="width:${share.toFixed(1)}%"></span></span>
        <span class="count">${num.format(count)}</span>
      </li>`;
    })
    .join("");
}

function renderRisk(metrics, ranking) {
  const risk = metrics.risk;
  $("risk-auc").textContent = risk.auc.toFixed(3);
  $("risk-base").textContent = `${one.format(risk.base_rate * 100)}%`;
  $("risk-top").textContent = `${one.format(risk.top_decile_rate * 100)}%`;
  $("risk-lift").textContent = `${one.format(risk.lift)}×`;

  baseRate = risk.base_rate;
  $("score-base").textContent = `${one.format(baseRate * 100)}%`;
  $("score-marker").style.left = `${Math.min(100, (baseRate / GAUGE_MAX) * 100).toFixed(1)}%`;

  const peak = Math.max(...ranking.rows.map((row) => row.probability), 0.001);
  $("ranking-body").innerHTML = ranking.rows
    .map((row) => {
      const share = (row.probability / peak) * 100;
      return `<tr>
        <td>${row.rank}</td>
        <td>${row.item}</td>
        <td class="num">${num.format(Math.round(row.latest_yield))}</td>
        <td class="num">${(row.last_change * 100).toFixed(1)}%</td>
        <td>
          <span class="prob">
            <span class="prob__track"><span class="prob__fill" style="width:${share.toFixed(1)}%"></span></span>
            <span class="prob__value">${one.format(row.probability * 100)}%</span>
          </span>
        </td>
      </tr>`;
    })
    .join("");
}

function renderMetrics(metrics) {
  $("metrics-body").innerHTML = metrics.models
    .map(
      (model) => `<tr>
        <td>${model.model}</td>
        <td class="num">${model.r2.toFixed(3)}</td>
        <td class="num">${num.format(Math.round(model.mae_kg_ha))}</td>
        <td class="num">${two.format(model.mape_pct)}</td>
      </tr>`
    )
    .join("");

  $("models-caption").textContent =
    `${metrics.test_observations} crop-year observations in ${metrics.test_years}.`;

  const canvas = $("mape-chart");
  new Chart(canvas, {
    type: "bar",
    data: {
      labels: metrics.models.map((model) => model.model.replace(" (last year)", "")),
      datasets: [
        {
          data: metrics.models.map((model) => model.mape_pct),
          backgroundColor: metrics.models.map((model) =>
            model.model.startsWith("Naive") ? COLORS.grey
              : model.model.startsWith("Linear") ? COLORS.gold
              : COLORS.green
          ),
          borderRadius: 6,
          maxBarThickness: 64,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, border: { color: COLORS.grid } },
        y: {
          grid: { color: COLORS.grid },
          border: { display: false },
          ticks: { callback: (value) => `${value}%` },
        },
      },
    },
  });
}

/* ------------------------------------------------------------------ crops */
async function loadCropList() {
  const catalogue = await get("/v1/crops?limit=200");
  $("crop-list").innerHTML = catalogue.items
    .map((crop) => `<option value="${crop.item}"></option>`)
    .join("");

  const preferred = catalogue.items.find((crop) => crop.item === "Wheat" && crop.forecastable);
  const fallback = catalogue.items.find((crop) => crop.forecastable);
  const start = preferred || fallback;

  const input = $("crop-input");
  input.value = start.item;
  currentCrop = start.item;

  input.addEventListener("change", () => {
    const value = input.value.trim();
    if (value && value !== currentCrop) {
      currentCrop = value;
      showForecast(value);
    }
  });

  showForecast(start.item);
}

async function showForecast(crop) {
  const encoded = encodeURIComponent(crop);
  try {
    const [forecast, history] = await Promise.all([
      get(`/v1/crops/${encoded}/forecast`),
      get(`/v1/crops/${encoded}/history`),
    ]);

    $("fc-latest").textContent = num.format(Math.round(forecast.latest_yield));
    $("fc-latest-sub").textContent = `kg/ha · ${forecast.latest_year}`;
    $("fc-year").textContent = forecast.target_year;
    $("fc-naive").textContent = num.format(Math.round(forecast.naive));
    $("fc-linear").textContent = num.format(Math.round(forecast.linear_regression));
    $("fc-rf").textContent = num.format(Math.round(forecast.random_forest));

    drawForecast(forecast, history);
    $("forecast-caption").textContent =
      `${forecast.item}: ${history.points.length} annual observations, ${history.points[0].year}–${forecast.latest_year}. `
      + `The three markers to the right are three different answers for ${forecast.target_year}.`;
  } catch (error) {
    // Never leave another crop's numbers on screen underneath a new name.
    ["fc-latest", "fc-naive", "fc-linear", "fc-rf"].forEach((id) => { $(id).textContent = "—"; });
    $("fc-latest-sub").textContent = "kg/ha";
    $("forecast-caption").textContent = `${crop}: ${error.message}`;
    if (forecastChart) {
      forecastChart.data.labels = [];
      forecastChart.data.datasets = [];
      forecastChart.update();
    }
  }
}

function drawForecast(forecast, history) {
  const years = history.points.map((point) => point.year);
  const values = history.points.map((point) => point.value);
  const labels = [...years, forecast.target_year];
  const lastIndex = years.length - 1;

  const actual = [...values, null];

  const branch = (value, color) => {
    const series = new Array(labels.length).fill(null);
    series[lastIndex] = values[lastIndex];
    series[lastIndex + 1] = value;
    return {
      data: series,
      borderColor: color,
      backgroundColor: color,
      borderWidth: 2,
      borderDash: [5, 4],
      pointRadius: 3,
      pointHoverRadius: 5,
      spanGaps: true,
      tension: 0,
    };
  };

  const datasets = [
    {
      label: "Actual",
      data: actual,
      borderColor: COLORS.text,
      backgroundColor: COLORS.text,
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.25,
    },
    { label: "Naive", ...branch(forecast.naive, COLORS.grey) },
    { label: "Linear regression", ...branch(forecast.linear_regression, COLORS.gold) },
    { label: "Random forest", ...branch(forecast.random_forest, COLORS.green) },
  ];

  if (forecastChart) {
    forecastChart.data.labels = labels;
    forecastChart.data.datasets = datasets;
    forecastChart.update();
    return;
  }

  forecastChart = new Chart($("forecast-chart"), {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top",
          align: "end",
          labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, pointStyle: "circle", padding: 16 },
        },
        tooltip: {
          backgroundColor: "#12171d",
          borderColor: "#2a323c",
          borderWidth: 1,
          titleColor: "#fff",
          bodyColor: "#c8d1da",
          padding: 10,
          callbacks: {
            label: (item) =>
              item.parsed.y == null ? null : `${item.dataset.label}: ${num.format(Math.round(item.parsed.y))} kg/ha`,
          },
        },
      },
      scales: {
        x: { grid: { display: false }, border: { color: COLORS.grid }, ticks: { maxRotation: 0, autoSkipPadding: 12 } },
        y: {
          grid: { color: COLORS.grid },
          border: { display: false },
          ticks: { callback: (value) => num.format(value) },
        },
      },
    },
  });
}

/* ------------------------------------------------------------------ scorer */
function wireScorer() {
  const inputs = [
    { id: "s1", out: "s1-out", key: "last_change" },
    { id: "s2", out: "s2-out", key: "previous_change" },
    { id: "s3", out: "s3-out", key: "gap_vs_3y_average" },
  ];

  const read = () => {
    const payload = {};
    inputs.forEach(({ id, out, key }) => {
      const value = Number($(id).value);
      $(out).textContent = `${value > 0 ? "+" : ""}${value} %`;
      payload[key] = value / 100;
    });
    return payload;
  };

  const run = async () => {
    const payload = read();
    try {
      const result = await post("/v1/risk/score", payload);
      const percent = result.probability * 100;
      $("score-value").textContent = `${one.format(percent)}%`;
      $("score-band").textContent = `${result.band} risk · probability of a drop above 10 %`;
      $("score-bar").style.width = `${Math.min(100, Math.max(2, (result.probability / GAUGE_MAX) * 100)).toFixed(1)}%`;
    } catch (error) {
      $("score-band").textContent = `Scoring unavailable — ${error.message}`;
    }
  };

  const debounced = debounce(run, 120);
  inputs.forEach(({ id }) => $(id).addEventListener("input", () => { read(); debounced(); }));
  read();
  run();
}

document.addEventListener("DOMContentLoaded", boot);
