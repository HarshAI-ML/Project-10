import logging
import traceback
import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from pipeline.fetchers.news_fetcher import NewsFetcher
from pipeline.fetchers.yfinance_fetcher import YFinanceBatchFetcher
from pipeline.models import PipelineRun
from pipeline.processors.cleaner import process_all_tickers
from pipeline.processors.forecaster import predict_all_tickers
from pipeline.processors.signals import compute_signals_all
from scripts.nifty500_top200 import ALL_STOCKS

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Orchestrates the Bronze/Silver/Gold data pipeline"

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            type=str,
            default="all",
            choices=["prices", "news", "full", "silver", "gold", "all"],
            help="Runs specific parts of the pipeline: prices, news, silver, gold, full/all",
        )
        parser.add_argument(
            "--period",
            type=str,
            default="1mo",
            help="Period to fetch (e.g., 1d, 1mo, 1y, max) - only used for prices",
        )
        parser.add_argument(
            "--interval",
            type=str,
            default="1d",
            help="Interval to fetch (e.g., 1d, 1h) - only used for prices",
        )

    def _run_silver(self, run):
        self.stdout.write("\n[Silver] Processing Bronze -> Silver (cleaning + indicators)...")
        result = process_all_tickers()
        self.stdout.write(
            f"    Silver done: {result['tickers_success']} tickers processed, "
            f"{result['tickers_failed']} failed, "
            f"{result['total_rows']} rows written"
        )

    def _run_gold(self, run):
        self.stdout.write("\n[Gold] Computing signals + forecasts...")

        self.stdout.write("  [1/2] Computing Buy/Sell/Hold signals...")
        sig_result = compute_signals_all()
        self.stdout.write(
            f"  Signals: {sig_result['success']} ok / "
            f"{sig_result['failed']} failed"
        )

        self.stdout.write("  [2/2] Running Linear Regression predictions (fast mode)...")
        pred_result = predict_all_tickers(horizon_days=1)
        self.stdout.write(
            f"  Predictions: {pred_result['success']} ok / "
            f"{pred_result['failed']} failed / "
            f"{pred_result['skipped']} skipped"
        )

    def handle(self, *args, **options):
        mode = options["mode"]
        period = options["period"]
        interval = options["interval"]

        self.stdout.write(self.style.SUCCESS(f"Starting pipeline run (Mode: {mode}, Period: {period})"))

        run_record = PipelineRun.objects.create(
            run_id=uuid.uuid4().hex,
            run_type=mode,
            status="RUNNING",
            started_at=timezone.now(),
        )

        try:
            if mode in ["all", "full", "prices"]:
                self.stdout.write("Running price fetcher...")
                all_tickers = [row[0] for row in ALL_STOCKS]
                fetcher = YFinanceBatchFetcher(batch_size=20, sleep_time=2.0)
                fetcher.fetch_prices(tickers=all_tickers, period=period, interval=interval)
                self.stdout.write("Price fetching complete.")

            if mode in ["all", "full", "news"]:
                self.stdout.write("Running news fetcher...")
                news_fetcher = NewsFetcher()
                news_fetcher.fetch_news()
                self.stdout.write("News fetching complete.")

            if mode in ["all", "full", "silver"]:
                self._run_silver(run_record)

            if mode in ["gold", "all"]:
                self._run_gold(run_record)

            run_record.status = "SUCCESS"
            run_record.message = f"Pipeline {mode} finished successfully."

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            logger.error(traceback.format_exc())
            run_record.status = "FAILED"
            run_record.message = str(e)

        finally:
            run_record.completed_at = timezone.now()
            run_record.save()
            self.stdout.write(self.style.SUCCESS(f"Pipeline run finished: {run_record.status}"))
