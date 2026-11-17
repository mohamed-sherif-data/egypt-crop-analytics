# Minimal R client. Requires: install.packages("httr2"); install.packages("jsonlite")
#
#   source("examples/client.R")
#   forecast <- get_json("/v1/crops/Wheat/forecast")

library(httr2)
library(jsonlite)

BASE <- Sys.getenv("CROP_API", unset = "http://127.0.0.1:8000")

get_json <- function(path, query = list()) {
  request(paste0(BASE, path)) |>
    req_url_query(!!!query) |>
    req_perform() |>
    resp_body_string() |>
    fromJSON(simplifyVector = FALSE)
}

post_json <- function(path, body) {
  request(paste0(BASE, path)) |>
    req_body_json(body) |>
    req_perform() |>
    resp_body_string() |>
    fromJSON(simplifyVector = FALSE)
}

health <- get_json("/v1/health")
cat(sprintf("healthy: %d crops, %s\n", health$crops, health$years))

forecast <- get_json("/v1/crops/Wheat/forecast")
cat(sprintf(
  "Wheat %d -> %d: naive %.0f | linear %.0f | forest %.0f kg/ha\n",
  forecast$latest_year, forecast$target_year,
  forecast$naive, forecast$linear_regression, forecast$random_forest
))

ranking <- get_json("/v1/risk/ranking", list(limit = 5))
for (row in ranking$rows) {
  cat(sprintf("%d. %-22s %.1f %%\n", row$rank, row$item, row$probability * 100))
}

scored <- post_json("/v1/risk/score", list(
  last_change = -0.12,
  previous_change = -0.05,
  gap_vs_3y_average = -0.08
))
cat(sprintf("scenario: %.1f %% (%s risk)\n", scored$probability * 100, scored$band))
