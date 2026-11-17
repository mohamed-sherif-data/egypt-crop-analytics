/**
 * Node 18+ (global fetch). Run:
 *   node examples/client.mjs
 *   node examples/client.mjs https://your-space.hf.space
 */

const BASE = (process.argv[2] ?? "http://127.0.0.1:8000").replace(/\/$/, "");

async function get(path) {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) throw new Error(`${path} → ${response.status} ${await response.text()}`);
  return response.json();
}

async function post(path, body) {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${path} → ${response.status} ${await response.text()}`);
  return response.json();
}

const health = await get("/v1/health");
console.log(`healthy: ${health.crops} crops, ${health.years}`);

const forecast = await get("/v1/crops/Wheat/forecast");
console.log(`Wheat ${forecast.latest_year} → ${forecast.target_year}`);
console.log(`  latest   ${Math.round(forecast.latest_yield)} kg/ha`);
console.log(`  naive    ${Math.round(forecast.naive)} kg/ha`);
console.log(`  linear   ${Math.round(forecast.linear_regression)} kg/ha`);
console.log(`  forest   ${Math.round(forecast.random_forest)} kg/ha`);

const ranking = await get("/v1/risk/ranking?limit=5");
for (const row of ranking.rows) {
  console.log(`${row.rank}. ${row.item.padEnd(22)} ${(row.probability * 100).toFixed(1)} %`);
}

const scored = await post("/v1/risk/score", {
  last_change: -0.12,
  previous_change: -0.05,
  gap_vs_3y_average: -0.08,
});
console.log(`scenario drop probability: ${(scored.probability * 100).toFixed(1)} % (${scored.band})`);
