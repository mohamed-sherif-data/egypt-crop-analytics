/* ============================================================================
   Egypt Crop Yield Analytics — client
   One job: show one crop's history, next-year forecast and decline risk.
   Talks only to the public API on the same origin. No framework, no build step.
   ========================================================================== */

const $ = (id) => document.getElementById(id);
const num = new Intl.NumberFormat("en-US");
const one = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const COLORS = {
  gold: "#d4af37",
  green: "#2fa37a",
  purple: "#8b6be0",
  grey: "#6b7885",
  text: "#eceef1",
  grid: "#1b222a",
  tick: "#8b98a5",
};

let chart = null;
let currentCrop = null;
let requestToken = 0;

/* ------------------------------------------------------------------ helpers */
async function get(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch { /* keep the status text */ }
    throw new Error(detail);
  }
  return response.json();
}

let statusTimer = null;

function status(state, text) {
  const bar = $("status");
  bar.dataset.state = state;
  $("status-text").textContent = text;
  bar.classList.remove("is-hidden");
  clearTimeout(statusTimer);
  // Once it is ready the pill has said its piece; get out of the way.
  if (state === "ready") {
    statusTimer = setTimeout(() => bar.classList.add("is-hidden"), 2600);
  }
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
    const catalogue = await get("/v1/crops?limit=200");
    $("crop-list").innerHTML = catalogue.items
      .map((crop) => `<option value="${crop.item}"></option>`)
      .join("");

    const start = pickStart(catalogue.items);
    $("crop-input").value = start;

    wireInput();
    await show(start, { updateUrl: true });
    status("ready", "Ready");
  } catch (error) {
    status("error", "Offline");
    $("caption").textContent = `Could not reach the API — ${error.message}`;
    console.error(error);
  }
}

/** A shared link wins; otherwise Wheat, otherwise the first forecastable crop. */
function pickStart(items) {
  const forecastable = items.filter((crop) => crop.forecastable);
  const requested = new URLSearchParams(location.search).get("crop");
  if (requested) {
    const match = forecastable.find(
      (crop) => crop.item.toLowerCase() === requested.toLowerCase()
    );
    if (match) return match.item;
  }
  const wheat = forecastable.find((crop) => crop.item === "Wheat");
  return (wheat || forecastable[0]).item;
}

function wireInput() {
  const input = $("crop-input");

  const submit = () => {
    const value = input.value.trim();
    if (!value) return;
    const match = [...$("crop-list").options].find(
      (option) => option.value.toLowerCase() === value.toLowerCase()
    );
    show(match ? match.value : value, { updateUrl: true });
  };

  $("picker").addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });

  // Choosing from the datalist fires input+change; Enter fires submit.
  input.addEventListener("change", submit);
}

/* -------------------------------------------------------------- the answer */
async function show(crop, { updateUrl }) {
  if (updateUrl) remember(crop);

  const token = ++requestToken;
  const encoded = encodeURIComponent(crop);
  $("picker-hint").textContent = "";

  try {
    const [forecast, history, risk] = await Promise.all([
      get(`/v1/crops/${encoded}/forecast`),
      get(`/v1/crops/${encoded}/history`),
      get(`/v1/crops/${encoded}/risk`),
    ]);
    if (token !== requestToken) return;   // a later crop already won

    currentCrop = crop;
    render(forecast, history, risk);
    status("ready", "Ready");
  } catch (error) {
    if (token !== requestToken) return;
    clear();
    $("caption").textContent =
      `“${crop}” could not be scored — ${error.message}. Try one of the 78 crops in the list.`;
    $("picker-hint").textContent = "Unknown crop";
  }
}

function render(forecast, history, risk) {
  document.title = `${forecast.item} — Egypt Crop Yield Analytics`;
  $("target-year").textContent = forecast.target_year;

  $("latest-value").textContent = num.format(Math.round(forecast.latest_yield));
  $("latest-sub").textContent = `kg/ha · ${forecast.latest_year}`;

  // The headline is the random-forest forecast, so the panel answers the
  // question directly; the honest comparison with the other two models sits
  // underneath, and the note explains that the naive baseline wins.
  $("forecast-label").textContent = `${forecast.item} · ${forecast.target_year}`;
  $("forecast-value").textContent = num.format(Math.round(forecast.random_forest));
  $("forecast-sub").textContent = "kg/ha · random forest";

  const percent = risk.probability * 100;
  $("risk-value").textContent = `${one.format(percent)}%`;
  $("risk-sub").textContent = `${risk.band} risk`;
  $("risk").dataset.band = risk.band;

  $("m-naive").textContent = `${num.format(Math.round(forecast.naive))} kg/ha`;
  $("m-linear").textContent = `${num.format(Math.round(forecast.linear_regression))} kg/ha`;
  $("m-forest").textContent = `${num.format(Math.round(forecast.random_forest))} kg/ha`;

  $("caption").textContent =
    `${forecast.item}: ${history.points.length} annual observations, `
    + `${history.points[0].year}–${forecast.latest_year}. `
    + `The dashed lines are the three answers for ${forecast.target_year}; `
    + `the linear model regresses toward the long-run average, so it reads low here.`;

  draw(forecast, history);
}

function clear() {
  ["latest-value", "forecast-value", "risk-value", "m-naive", "m-linear", "m-forest"]
    .forEach((id) => { $(id).textContent = "—"; });
  $("latest-sub").textContent = "kg/ha";
  $("forecast-sub").textContent = "kg/ha";
  $("risk-sub").textContent = "chance next year";
  delete $("risk").dataset.band;
  if (chart) {
    chart.data.labels = [];
    chart.data.datasets = [];
    chart.update();
  }
}

function remember(crop) {
  try {
    const url = new URL(location.href);
    url.searchParams.set("crop", crop);
    history.replaceState(null, "", url);
  } catch { /* history is unavailable in some embedded views */ }
}

/* ------------------------------------------------------------------- chart */
function draw(forecast, data) {
  const years = data.points.map((point) => point.year);
  const values = data.points.map((point) => point.value);
  const labels = [...years, forecast.target_year];
  const last = years.length - 1;

  const branch = (value, color, label) => {
    const series = new Array(labels.length).fill(null);
    series[last] = values[last];
    series[last + 1] = value;
    return {
      label,
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
      label: "Observed",
      data: [...values, null],
      borderColor: COLORS.text,
      backgroundColor: COLORS.text,
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.25,
    },
    branch(forecast.naive, COLORS.gold, "Naive"),
    branch(forecast.linear_regression, COLORS.purple, "Linear"),
    branch(forecast.random_forest, COLORS.green, "Forest"),
  ];

  if (chart) {
    chart.data.labels = labels;
    chart.data.datasets = datasets;
    chart.update();
    return;
  }

  chart = new Chart($("chart"), {
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
          labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true, pointStyle: "circle", padding: 14 },
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
        x: { grid: { display: false }, border: { color: COLORS.grid }, ticks: { maxRotation: 0, autoSkipPadding: 14 } },
        y: { grid: { color: COLORS.grid }, border: { display: false }, ticks: { callback: (value) => num.format(value) } },
      },
    },
  });
}

document.addEventListener("DOMContentLoaded", boot);
