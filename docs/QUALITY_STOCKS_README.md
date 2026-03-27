# Quality Stocks Feature README

## What This Feature Does

The Quality Stocks feature helps a logged-in user:

1. Shortlist top candidates from a portfolio (`snapshot`).
2. Generate and persist detailed quality reports for selected stocks (`generate` / `rerun`).
3. Browse report summaries (`list`) and full report details (`retrieve`).

Core implementation lives in `backend/api/quality_stocks.py` and is exposed through `QualityStockViewSet` in `backend/api/views.py`.

## Data Model

Quality reports are stored in `portfolio.QualityStock` with one row per `(portfolio, stock)`:

- `ai_rating` (float)
- `buy_signal` (`BUY` / `HOLD` / `SELL`)
- `report_json` (LLM/deterministic narrative fields)
- `graphs_data` (price history + sector comparison metrics)
- `generated_at` (auto-updated timestamp)
- `selected_by_user` (boolean)

Uniqueness is enforced by constraint `uq_quality_stock_portfolio_stock`.

## Endpoints

Base route is under API router: `quality-stocks`.

1. `POST /api/quality-stocks/snapshot/`
- Body: `{ "portfolio_id": <int> }`
- Returns a `shortlist` of top 3 portfolio candidates (not persisted to `QualityStock`).

2. `POST /api/quality-stocks/generate/`
- Body: `{ "portfolio_id": <int>, "stock_ids": [<int>, ...] }`
- Generates report(s), persists/upserts `QualityStock`, and returns detailed result rows.

3. `POST /api/quality-stocks/{id}/rerun/`
- Regenerates one existing report while keeping the same stock+portfolio pair.

4. `GET /api/quality-stocks/`
- Query params:
  - `portfolio` (optional portfolio id)
  - `signal` (`all`, `BUY`, `HOLD`, `SELL`; default `all`)
- Returns report list with live-enriched metrics.

5. `GET /api/quality-stocks/{id}/`
- Returns one detailed quality report payload.

## How Snapshot Works

`build_quality_snapshot(portfolio)` does:

1. Load all `PortfolioStock` rows for the portfolio.
2. Join analytics data in bulk:
- latest prices
- latest forecasts
- latest signals
- latest sentiment
- latest fundamentals
- ~120 days cleaned price history
3. Compute trend metrics per ticker:
- `momentum_30d`
- `momentum_90d`
- `avg_volume_20d`
- `volume_trend_pct`
4. Compute ranking score via `_score_snapshot_row`:
- `expected_change_pct * 2`
- valuation bonus from lower PE
- momentum bonus
- signal bonus (`BUY` > `HOLD` > `SELL`)
5. Return top 3 ranked stocks.

Important: during snapshot, `_ensure_stock_record(...)` upserts `Stock` rows so each ticker has a concrete `stock_id` for the next step.

## How Generate Works

`generate_quality_reports(...)` runs a 3-stage pipeline (`fetch -> analyze -> persist`), using LangGraph when available and a sequential fallback otherwise.

### 1) Fetch stage (`_fetch_quality_node`)

- Validates requested `stock_ids` belong to the given portfolio tickers.
- Builds per-stock payload with:
  - fundamentals
  - current price / forecast
  - market signal
  - trend metrics from recent history
  - sector averages
  - graph-ready data

### 2) Analyze stage (`_analyze_quality_node`)

For each stock:

- Calls `_run_llm_quality_report(...)` with structured JSON input and `QUALITY_STOCK_SYSTEM_PROMPT`.
- Expects strict JSON output:
  - `symbol`, `ai_rating`, `signal`, `justification`, `risks`, `catalysts`, `key_metrics_summary`
- Normalizes values (`signal`, rating precision, top-2 risks/catalysts).

If LLM output fails or is malformed, it falls back to `_deterministic_quality_report(...)`, which computes:

- a bounded score from fundamentals + momentum + signal bias
- recommendation thresholds for BUY/HOLD/SELL
- generated risks, catalysts, justification, and summary

### 3) Persist stage (`_persist_quality_node`)

- `update_or_create` on `(portfolio, stock)` in `QualityStock`.
- Stores:
  - AI rating/signal
  - `report_json`
  - `graphs_data`
  - `generated_at=now`
  - `selected_by_user`

## How List/Detail Payloads Are Built

### List (`build_quality_stock_rows`)

Starts from saved `QualityStock` rows, then enriches each with current analytics:

- latest price, forecast, market signal
- fundamentals PE
- sentiment
- 365-day high/low and discount %

### Detail (`get_quality_stock_detail`)

Builds full response with:

- list-row summary fields
- `report_json`, `graphs_data`
- expanded `key_financials`
- sector average metrics

## LLM and Reliability Behavior

- LLM call is made through `api.chatbot_service._call_chat_model(...)`.
- If provider/model response is invalid, the system still returns a usable report via deterministic fallback.
- This means report generation is resilient even when external LLM providers are unavailable.

## Permissions and Ownership Rules

- All operations are authenticated (`IsAuthenticated`).
- Querysets are always filtered to `portfolio__user=request.user`.
- `generate` and `snapshot` both verify portfolio ownership.
- `retrieve`/`rerun` fail with 404 if report does not belong to current user.

## Typical Frontend Flow

1. Call `snapshot` for selected portfolio.
2. Show shortlist and let user pick stock(s).
3. Call `generate` with selected `stock_ids`.
4. Render generated cards from response.
5. Use `list` for dashboard refresh and `retrieve` for detail page.
6. Use `rerun` to refresh one report.

