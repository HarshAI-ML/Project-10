import json
import logging
import time
import uuid
from datetime import date
from datetime import timezone as dt_timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pandas as pd
import yfinance as yf
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from pipeline.fetchers.news_fetcher import fetch_and_store_news
from pipeline.models import BronzeStockPrice, PipelineRun
from portfolio.models import StockMaster
from scripts.nifty500_top200 import ALL_STOCKS


class PipelineLogFormatter(logging.Formatter):
    """Log formatter: TIMESTAMP | LEVEL | TICKER | DATA_TYPE | DETAILS"""

    def format(self, record):
        if not hasattr(record, "ticker"):
            record.ticker = "GLOBAL"
        if not hasattr(record, "data_type"):
            record.data_type = "system"
        return super().format(record)


class Command(BaseCommand):
    help = (
        "Incremental Bronze fetch for prices + news.\n"
        "Stores true hourly candles using BronzeStockPrice.candle_at while retaining date bucket."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            type=str,
            default="5d",
            help="yfinance period for overlap window (e.g., 1d, 5d, 1mo). Default=5d",
        )
        parser.add_argument(
            "--interval",
            type=str,
            default="1h",
            help="yfinance interval. Default=1h",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional limit for number of tickers (debug runs).",
        )
        parser.add_argument(
            "--skip-news",
            action="store_true",
            help="Skip incremental news fetch.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=0.2,
            help="Sleep between tickers in seconds. Default=0.2",
        )

    def _setup_logger(self) -> tuple[logging.Logger, Path]:
        logs_dir = Path(settings.BASE_DIR) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / "fetch_hourly_incremental.log"

        logger = logging.getLogger("pipeline.fetch_hourly_incremental")
        logger.setLevel(logging.INFO)
        logger.propagate = False

        # Avoid duplicate handlers across repeated command executions in same process.
        logger.handlers.clear()

        file_handler = RotatingFileHandler(
            filename=log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            PipelineLogFormatter("%(asctime)s | %(levelname)s | %(ticker)s | %(data_type)s | %(message)s")
        )
        logger.addHandler(file_handler)
        return logger, log_path

    @staticmethod
    def _to_dt(ts):
        """Normalize pandas timestamp to UTC-naive datetime."""
        stamp = pd.Timestamp(ts)
        if stamp.tz is not None:
            stamp = stamp.tz_convert("UTC").tz_localize(None)
        else:
            stamp = stamp.tz_localize(None)
        dt = stamp.to_pydatetime()
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone=dt_timezone.utc)
        return dt

    @staticmethod
    def _to_date(ts) -> date:
        return Command._to_dt(ts).date()

    def _fetch_incremental_prices(
        self,
        ticker: str,
        company: str,
        run_id: str,
        period: str,
        interval: str,
        logger: logging.Logger,
    ) -> dict:
        tlog = logging.LoggerAdapter(logger, {"ticker": ticker, "data_type": "prices"})

        last_candle_at = (
            BronzeStockPrice.objects
            .filter(ticker=ticker)
            .exclude(candle_at__isnull=True)
            .order_by("-candle_at")
            .values_list("candle_at", flat=True)
            .first()
        )
        last_date = (
            BronzeStockPrice.objects
            .filter(ticker=ticker)
            .order_by("-date")
            .values_list("date", flat=True)
            .first()
        )

        # Pull a small overlap window; dedupe by date before insert.
        hist = yf.Ticker(ticker).history(
            period=period,
            interval=interval,
            auto_adjust=True,
            actions=False,
        )

        if hist is None or hist.empty:
            tlog.info("No new data (empty response)")
            return {"rows_added": 0, "status": "no_new_data", "last_date": str(last_date) if last_date else None}

        hist = hist.dropna(how="all")
        if hist.empty:
            tlog.info("No new data (all-null frame)")
            return {"rows_added": 0, "status": "no_new_data", "last_date": str(last_date) if last_date else None}

        hist.columns = [str(c).lower() for c in hist.columns]
        if "close" not in hist.columns:
            tlog.info("No new data (close column missing)")
            return {"rows_added": 0, "status": "no_new_data", "last_date": str(last_date) if last_date else None}

        hist = hist[hist["close"].notna()].copy()
        if hist.empty:
            tlog.info("No new data (close all null)")
            return {"rows_added": 0, "status": "no_new_data", "last_date": str(last_date) if last_date else None}

        candidate_rows = []
        for idx, row in hist.sort_index().iterrows():
            candle_at = self._to_dt(idx)
            day = candle_at.date()
            if last_candle_at and candle_at <= last_candle_at:
                continue
            if (not last_candle_at) and last_date and day < last_date:
                continue
            candidate_rows.append((candle_at, day, row))

        if not candidate_rows:
            tlog.info("No new data (already up to date)")
            return {"rows_added": 0, "status": "no_new_data", "last_date": str(last_date) if last_date else None}

        candidate_ts = [entry[0] for entry in candidate_rows]
        existing_ts = set(
            BronzeStockPrice.objects
            .filter(ticker=ticker, candle_at__in=candidate_ts)
            .values_list("candle_at", flat=True)
        )

        objects_to_create = []
        for candle_at, day, row in candidate_rows:
            if candle_at in existing_ts:
                continue
            volume = row.get("volume")
            if pd.isna(volume):
                volume = None
            elif volume is not None:
                volume = int(volume)

            objects_to_create.append(
                BronzeStockPrice(
                    ticker=ticker,
                    company=company,
                    date=day,
                    candle_at=candle_at,
                    open=None if pd.isna(row.get("open")) else float(row.get("open")),
                    high=None if pd.isna(row.get("high")) else float(row.get("high")),
                    low=None if pd.isna(row.get("low")) else float(row.get("low")),
                    close=float(row.get("close")),
                    volume=volume,
                    source="yfinance",
                    fetch_run_id=run_id,
                )
            )

        if not objects_to_create:
            tlog.info("No new data (dedup removed all rows)")
            return {"rows_added": 0, "status": "no_new_data", "last_date": str(last_date) if last_date else None}

        BronzeStockPrice.objects.bulk_create(objects_to_create, batch_size=200)
        tlog.info(
            "Fetched %s new rows (%s to %s)",
            len(objects_to_create),
            objects_to_create[0].candle_at,
            objects_to_create[-1].candle_at,
        )
        return {
            "rows_added": len(objects_to_create),
            "status": "success",
            "last_date": str(objects_to_create[-1].date),
            "last_candle_at": objects_to_create[-1].candle_at.isoformat() if objects_to_create[-1].candle_at else None,
        }

    def handle(self, *args, **options):
        started = timezone.now()
        logger, log_path = self._setup_logger()

        ticker_rows = list(
            StockMaster.objects
            .filter(is_active=True)
            .exclude(ticker__isnull=True)
            .exclude(ticker="")
            .values_list("ticker", "name")
        )
        if not ticker_rows:
            ticker_rows = [(t, n) for (t, n, _s, _g) in ALL_STOCKS]

        if options["limit"]:
            ticker_rows = ticker_rows[: options["limit"]]

        run_id = uuid.uuid4().hex
        run = PipelineRun.objects.create(
            run_id=run_id,
            run_type="hourly_incremental",
            status="running",
            stocks_total=len(ticker_rows),
            stocks_success=0,
            stocks_failed=0,
        )

        stats = {
            "run_id": run_id,
            "run_type": "hourly_incremental",
            "period": options["period"],
            "interval": options["interval"],
            "total_tickers": len(ticker_rows),
            "successful": 0,
            "failed": 0,
            "no_new_data": 0,
            "total_rows_added": 0,
            "failed_tickers": [],
            "tickers": {},
            "news": {"fetched": 0, "new": 0, "skipped": 0, "status": "skipped"},
            "log_path": str(log_path),
        }

        self.stdout.write("Using timestamp-based incremental fetch on BronzeStockPrice.candle_at.")

        for idx, (ticker, company) in enumerate(ticker_rows, start=1):
            try:
                result = self._fetch_incremental_prices(
                    ticker=ticker,
                    company=company or ticker,
                    run_id=run_id,
                    period=options["period"],
                    interval=options["interval"],
                    logger=logger,
                )
                stats["tickers"][ticker] = result
                if result["status"] == "success":
                    stats["successful"] += 1
                    stats["total_rows_added"] += int(result["rows_added"])
                else:
                    stats["successful"] += 1
                    stats["no_new_data"] += 1
            except Exception as exc:
                logging.LoggerAdapter(logger, {"ticker": ticker, "data_type": "prices"}).error(
                    "Fetch failed: %s", exc
                )
                stats["failed"] += 1
                stats["failed_tickers"].append(ticker)
                stats["tickers"][ticker] = {"status": "failed", "error": str(exc)}

            # Persist progress after each ticker as requested.
            run.stocks_success = stats["successful"]
            run.stocks_failed = stats["failed"]
            run.notes = json.dumps(
                {
                    "progress": {
                        "completed": idx,
                        "total": len(ticker_rows),
                    },
                    "totals": {
                        "successful": stats["successful"],
                        "failed": stats["failed"],
                        "no_new_data": stats["no_new_data"],
                        "total_rows_added": stats["total_rows_added"],
                    },
                }
            )
            run.save(update_fields=["stocks_success", "stocks_failed", "notes"])
            time.sleep(max(options["sleep"], 0))

        if not options["skip_news"]:
            nlog = logging.LoggerAdapter(logger, {"ticker": "GLOBAL", "data_type": "news"})
            try:
                news_result = fetch_and_store_news()
                stats["news"] = {**news_result, "status": "success"}
                nlog.info(
                    "Fetched %(new)s new articles (%(fetched)s total fetched, %(skipped)s skipped existing)",
                    news_result,
                )
            except Exception as exc:
                stats["news"] = {"status": "failed", "error": str(exc)}
                nlog.error("News fetch failed: %s", exc)

        ended = timezone.now()
        duration = ended - started

        stats["duration_seconds"] = round(duration.total_seconds(), 2)
        stats["started_at"] = started.isoformat()
        stats["completed_at"] = ended.isoformat()

        if stats["failed"] == 0 and stats["news"].get("status") != "failed":
            final_status = "success"
        elif stats["successful"] > 0:
            final_status = "partial"
        else:
            final_status = "failed"

        run.status = final_status
        run.completed_at = ended
        run.stocks_success = stats["successful"]
        run.stocks_failed = stats["failed"]
        run.notes = json.dumps(stats)
        if stats["failed_tickers"]:
            run.error_log = json.dumps({"failed_tickers": stats["failed_tickers"]})
        run.save()

        self.stdout.write("\n=== Hourly Fetch Complete ===")
        self.stdout.write(f"Run ID: {run_id}")
        self.stdout.write(f"Total tickers: {stats['total_tickers']}")
        self.stdout.write(f"Successful: {stats['successful']}")
        self.stdout.write(f"Failed: {stats['failed']}")
        self.stdout.write(f"No new data: {stats['no_new_data']}")
        self.stdout.write(f"Total rows added: {stats['total_rows_added']}")
        self.stdout.write(f"Failed tickers: {stats['failed_tickers']}")
        self.stdout.write(f"Duration: {duration}")
        self.stdout.write(f"Log: {log_path}")
