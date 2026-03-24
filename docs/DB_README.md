# Database README

This document describes the backend database structure across apps, including medallion pipeline tables and serving tables.

## Scope

- Project path: `backend/`
- Framework: Django ORM
- Main DB: SQLite in local dev (`backend/db.sqlite3`)
- Includes Django built-in auth/session/token tables plus project tables below.

## High-Level Architecture

The project uses two main data domains:

- Portfolio domain (`portfolio` app): user portfolios and tracked stocks
- Analytics/pipeline domain (`pipeline` + `analytics` apps): Bronze -> Silver -> Gold market data and prediction support

## App-Wise Table Inventory

## `portfolio` app

### `Portfolio`

- Purpose: user-owned portfolio container
- Key fields:
  - `user` (FK -> `auth_user`)
  - `name`, `description`
  - `is_default`, `portfolio_type`, `geography`
- Constraints:
  - `unique_together (user, name)`

### `Stock`

- Purpose: tracked stock entity used by APIs/UI
- Key fields:
  - `portfolio` (nullable FK -> `Portfolio`) (legacy linkage)
  - `symbol` (unique)
  - price/prediction serving fields (`current_price`, `predicted_price_1d`, `prediction_status`, etc.)
  - catalogue helpers (`ticker`, `name`, `geography`, `is_active`)
- Notes:
  - Current implementation also uses `PortfolioStock` as the preferred portfolio membership mapping.

### `PortfolioStock`

- Purpose: normalized mapping between `Portfolio` and stock catalogue
- Key fields:
  - `portfolio` (FK -> `Portfolio`)
  - `stock_master` (nullable FK -> `StockMaster`)
  - denormalized snapshot columns: `ticker`, `company_name`, `sector`, `geography`
- Constraints:
  - `unique_together (portfolio, ticker)`

### `StockMaster`

- Purpose: canonical stock universe (400 approved stocks)
- Key fields:
  - `ticker` (unique, indexed)
  - `name`, `sector`, `geography`, `is_active`

## `pipeline` app (Medallion)

### Bronze Tables

### `BronzeStockPrice`

- Raw OHLCV ingestion
- Key fields: `ticker`, `date`, `open/high/low/close/volume`, `source`, `fetch_run_id`
- Indexes: `(ticker, date)`

### `BronzeNewsArticle`

- Raw news ingestion
- Key fields: `article_id` (unique), `title`, `url`, `published_at`, `company_tags`, `source`

### `BronzeStockFundamentals`

- Raw fundamentals snapshots
- Key fields: valuation/profitability/growth/risk metrics, `fetched_at`
- Indexes: `ticker`

### Silver Table

### `SilverCleanedPrice`

- Cleaned/enriched price series derived from Bronze prices
- Key fields:
  - OHLCV copy
  - indicators (`daily_return`, `ma_20`, `rsi_14`, `macd`, Bollinger, volatility, etc.)
  - metadata (`processed_at`, `source_run_id`)
- Constraints:
  - `unique_together (ticker, date)`
- Indexes:
  - `(ticker, date)`

### Gold Tables

### `GoldStockSignal`

- Rule-based BUY/SELL/HOLD outputs from Silver indicators
- Key fields:
  - `ticker`, `date`, `signal`, `confidence`
  - component signals + snapshot indicators
- Constraints:
  - `unique_together (ticker, date)`
- Indexes:
  - `(ticker, date)`

### `GoldForecastResult`

- Forecast outputs from Silver features
- Key fields:
  - `ticker`, `forecast_date`, `predicted_price`, `expected_change_pct`, `confidence_r2`, `model_type`
- Constraints:
  - `unique_together (ticker, forecast_date, model_type)`
- Indexes:
  - `(ticker, forecast_date)`

### `GoldStockInsight`

- Portfolio-facing insight payload (serving table)
- Key fields:
  - `ticker`, `date`, `pe_ratio`, `discount_level`, `opportunity_score`, `graph_data`
  - timestamps: `computed_at`, `updated_at`
- Constraints:
  - `unique_together (ticker, date)`
- Indexes:
  - `(ticker, date)`

### Pipeline Metadata

### `PipelineRun`

- Tracks run execution status and counters
- Key fields: `run_id`, `run_type`, `status`, `started_at`, `completed_at`, error/notes fields

## `analytics` app

### `PredictionResultCache`

- Caches expensive prediction API output (plots + JSON payloads)
- Constraints:
  - `unique_together (stock_symbol, model_type, prediction_frequency, historical_period)`

### `PredictionModelState`

- Tracks model freshness (`last_trained_at`) per model type

### `StockAnalytics` (Legacy Compatibility)

- Legacy insights table tied to `Stock` (`OneToOne`)
- Still present for backward compatibility/mirroring, but active serving has been moved to `pipeline.GoldStockInsight`.

## `accounts`, `api`, `autosignal` models

- No custom persistent models currently defined in:
  - `accounts.models`
  - `api.models`
  - `autosignal.models`

## Key Relationships

- `auth_user` 1 -> N `Portfolio`
- `Portfolio` 1 -> N `PortfolioStock`
- `PortfolioStock` N -> 1 `StockMaster` (nullable)
- `Portfolio` 1 -> N `Stock` (legacy nullable FK model path)
- `Stock` 1 -> 1 `StockAnalytics` (legacy)

Medallion tables are mostly joined by `ticker` + date keys (string/date based), not strict foreign keys to `StockMaster`.

## Data Lifecycle (Commands)

Typical full lifecycle:

```bash
python manage.py migrate
python manage.py run_pipeline --mode=all
python manage.py run_analytics
```

Layer-specific:

- Bronze prices/news/fundamentals:
  - `run_pipeline --mode=prices`
  - `run_pipeline --mode=news`
  - `fetch_fundamentals`
- Silver:
  - `run_pipeline --mode=silver`
- Gold:
  - `run_pipeline --mode=gold`
- Analytics refresh:
  - `run_analytics [--skip-prediction] [--limit N]`

## Serving Source of Truth

For current portfolio/stock insight serving, use Gold tables:

- `GoldStockInsight`
- `GoldStockSignal`
- `GoldForecastResult`

`StockAnalytics` should be treated as compatibility/legacy data unless explicitly needed.

## Suggested Maintenance

- Keep medallion commands as canonical write path.
- Avoid direct ad-hoc writes into `SilverCleanedPrice` or legacy `StockAnalytics`.
- If you plan hard deprecation, migrate remaining consumers away from `StockAnalytics` before dropping it.
