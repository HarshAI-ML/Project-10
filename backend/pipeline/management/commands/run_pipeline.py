import logging
import traceback
import uuid

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from pipeline.fetchers.yfinance_fetcher import YFinanceBatchFetcher
from pipeline.models import PipelineRun
from pipeline.processors.cleaner import process_all_tickers
from pipeline.processors.forecaster import predict_all_tickers
from pipeline.processors.insights import compute_insights_all
from pipeline.processors.sentiment import aggregate_sector_sentiment, compute_sentiment_all
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
            choices=["prices", "news", "full", "silver", "gold", "sentiment", "all"],
            help="Runs specific parts of the pipeline: prices, news, silver, gold, sentiment, full/all",
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
        parser.add_argument(
            "--text-mode",
            type=str,
            default="both",
            choices=["title", "both"],
            help="FinBERT input mode for sentiment: title only (fast) or title+description (balanced).",
        )
        parser.add_argument(
            "--with-analytics",
            action="store_true",
            help="Also run run_analytics at the end of pipeline execution.",
        )
        parser.add_argument(
            "--analytics-skip-prediction",
            action="store_true",
            help="When used with --with-analytics, skip prediction refresh in run_analytics.",
        )
        parser.add_argument(
            "--analytics-limit",
            type=int,
            default=0,
            help="When used with --with-analytics, process only first N stocks in run_analytics (0 = all).",
        )

    def _run_silver(self, run):
        self.stdout.write("\n[Silver] Processing Bronze -> Silver (cleaning + indicators)...")
        result = process_all_tickers()
        self.stdout.write(
            f"    Silver done: {result['tickers_success']} tickers processed, "
            f"{result['tickers_failed']} failed, "
            f"{result['total_rows']} rows written"
        )

    def _run_news(self, run):
        self.stdout.write("\n[2/2] Fetching news...")
        from pipeline.fetchers.news_fetcher import fetch_and_store_news

        result = fetch_and_store_news()
        self.stdout.write(
            f"  News done: {result['new']} new articles | "
            f"{result['skipped']} already existed | "
            f"{result['fetched']} total fetched"
        )

    def _run_gold(self, run):
        self.stdout.write("\n[Gold] Computing signals + forecasts + insights...")

        self.stdout.write("  [1/3] Computing Buy/Sell/Hold signals...")
        sig_result = compute_signals_all()
        self.stdout.write(
            f"  Signals: {sig_result['success']} ok / "
            f"{sig_result['failed']} failed"
        )

        self.stdout.write("  [2/3] Running Linear Regression predictions (fast mode)...")
        pred_result = predict_all_tickers(horizon_days=1)
        self.stdout.write(
            f"  Predictions: {pred_result['success']} ok / "
            f"{pred_result['failed']} failed / "
            f"{pred_result['skipped']} skipped"
        )

        self.stdout.write("  [3/3] Computing Gold insights...")
        insight_result = compute_insights_all()
        self.stdout.write(
            f"  Insights: {insight_result['success']} ok / "
            f"{insight_result['failed']} failed"
        )

    def _run_sentiment(self, run, text_mode="both"):
        self.stdout.write(f"\n[Sentiment] Running FinBERT + price signals (text_mode={text_mode})...")
        result = compute_sentiment_all(text_mode=text_mode)
        self.stdout.write(
            self.style.SUCCESS(
                f"  Stock sentiment: {result['success']} ok / "
                f"{result['failed']} failed / "
                f"{result['no_news']} price-only (no news)"
            )
        )

        sec_result = aggregate_sector_sentiment()
        self.stdout.write(
            self.style.SUCCESS(
                f"  Sector sentiment: {sec_result['sectors']} sectors written to Gold"
            )
        )

    def _run_analytics(self, skip_prediction=False, limit=0):
        self.stdout.write(
            f"\n[Analytics] Running stock analytics refresh "
            f"(skip_prediction={skip_prediction}, limit={limit or 'all'})..."
        )
        call_command(
            "run_analytics",
            skip_prediction=bool(skip_prediction),
            limit=int(limit or 0),
        )

    def handle(self, *args, **options):
        mode = options["mode"]
        period = options["period"]
        interval = options["interval"]
        text_mode = options["text_mode"]
        with_analytics = bool(options.get("with_analytics"))
        analytics_skip_prediction = bool(options.get("analytics_skip_prediction"))
        analytics_limit = int(options.get("analytics_limit") or 0)

        self.stdout.write(self.style.SUCCESS(f"Starting pipeline run (Mode: {mode}, Period: {period})"))

        run_record = PipelineRun.objects.create(
            run_id=uuid.uuid4().hex,
            run_type=mode,
            status="running",
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
                self._run_news(run_record)

            if mode in ["all", "full", "silver"]:
                self._run_silver(run_record)

            if mode in ["gold", "all"]:
                self._run_gold(run_record)

            if mode in ["sentiment", "all"]:
                self._run_sentiment(run_record, text_mode=text_mode)

            if with_analytics:
                self._run_analytics(
                    skip_prediction=analytics_skip_prediction,
                    limit=analytics_limit,
                )

            run_record.status = "success"
            run_record.notes = f"Pipeline {mode} finished successfully."

        except Exception as exc:
            logger.error("Pipeline failed: %s", exc)
            logger.error(traceback.format_exc())
            run_record.status = "failed"
            run_record.error_log = traceback.format_exc()
            run_record.notes = str(exc)

        finally:
            run_record.completed_at = timezone.now()
            run_record.save(update_fields=["status", "completed_at", "notes", "error_log"])
            self.stdout.write(self.style.SUCCESS(f"Pipeline run finished: {run_record.status}"))
