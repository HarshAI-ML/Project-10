# Hourly Incremental Fetch (`fetch_hourly_incremental`)

This command performs incremental Bronze ingestion for prices (and optionally news) using per-ticker checkpoints.

Command:

```bash
python manage.py fetch_hourly_incremental
```

Location:

- `backend/pipeline/management/commands/fetch_hourly_incremental.py`

## What It Updates

## 1) Bronze Prices

Table:

- `pipeline.BronzeStockPrice`

Strategy:

- Uses latest `candle_at` per ticker as checkpoint.
- Pulls recent data from yfinance (`period=5d`, `interval=1h` by default).
- Keeps only rows with `candle_at > last_candle_at`.
- Inserts append-only rows with:
  - `ticker`
  - `company`
  - `date` (day bucket, backward compatibility)
  - `candle_at` (true candle timestamp)
  - OHLCV
  - `fetch_run_id`

Deduplication:

- DB-level unique constraint on `(ticker, candle_at)` prevents duplicates.

## 2) Bronze News (optional)

Table:

- `pipeline.BronzeNewsArticle`

Strategy:

- Uses existing RSS fetcher.
- Appends only new rows.
- Dedupes by `article_id` with conflict-safe insert.

Skip news:

```bash
python manage.py fetch_hourly_incremental --skip-news
```

## Checkpointing + Progress

Each run creates a `PipelineRun` row:

- `run_type = "hourly_incremental"`
- `status` transitions: `running -> success/partial/failed`
- `notes` stores JSON progress and final summary

Progress is saved after each ticker, including:

- completed/total tickers
- successful/failed/no-new-data counts
- rows added

## Logging

Rotating log file:

- `backend/logs/fetch_hourly_incremental.log`

Format:

```text
TIMESTAMP | LEVEL | TICKER | DATA_TYPE | DETAILS
```

Examples:

```text
2026-03-24 15:23:52,461 | INFO | BAJAJ-AUTO.NS | prices | Fetched 7 new rows (2026-03-24 03:45:00+00:00 to 2026-03-24 09:45:00+00:00)
2026-03-24 15:25:10,141 | ERROR | XYZ.NS | prices | Fetch failed: ...
2026-03-24 15:26:17,687 | INFO | GLOBAL | news | Fetched 12 new articles (120 total fetched, 108 skipped existing)
```

## CLI Options

```bash
python manage.py fetch_hourly_incremental \
  --period 5d \
  --interval 1h \
  --sleep 0.2 \
  --limit 50
```

Arguments:

- `--period` (default `5d`): yfinance overlap window.
- `--interval` (default `1h`): yfinance candle interval.
- `--limit` (optional): process first N tickers only (debug/smoke).
- `--skip-news` (flag): skip news fetch.
- `--sleep` (default `0.2`): pause between tickers in seconds.

## Typical Schedules

Cron (Linux):

```bash
0 * * * * cd /path/to/backend && python manage.py fetch_hourly_incremental >> /var/log/fetch_hourly_cron.log 2>&1
```

Windows Task Scheduler:

- Program: `python`
- Args: `manage.py fetch_hourly_incremental`
- Start in: `<repo>/backend`
- Trigger: hourly

## Summary Output

At run end, console prints:

- Run ID
- Total tickers
- Successful / Failed / No new data
- Total rows added
- Failed tickers
- Duration
- Log path

## Notes

- This command writes only Bronze layer data.
- Silver/Gold are not recomputed here.
- For full pipeline refresh after hourly ingestion, run:

```bash
python manage.py run_pipeline --mode=silver
python manage.py run_pipeline --mode=gold
```

