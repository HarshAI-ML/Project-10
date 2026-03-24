from django.core.management.base import BaseCommand
from analytics.data_access import has_data
from analytics.services.pipeline import generate_and_persist_stock_analytics
from analytics.services.prediction import refresh_stock_prediction
from portfolio.models import Stock


class Command(BaseCommand):
    help = "Run live analytics pipeline and persist Gold insights (with StockAnalytics compatibility mirror)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-prediction",
            action="store_true",
            help="Only compute analytics insights; skip prediction refresh.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Process only first N stocks (0 = all).",
        )

    def handle(self, *args, **options):
        skip_prediction = bool(options.get("skip_prediction"))
        limit = int(options.get("limit") or 0)

        queryset = Stock.objects.all().order_by("id")
        if limit > 0:
            queryset = queryset[:limit]

        total = queryset.count()
        processed = 0
        success = 0
        no_data = 0
        failed = 0

        self.stdout.write(
            f"Starting run_analytics for {total} stocks "
            f"(skip_prediction={skip_prediction}, limit={limit or 'all'})"
        )

        for stock in queryset.iterator():
            processed += 1
            symbol = stock.symbol
            self.stdout.write(f"[{processed}/{total}] {symbol}")

            try:
                if not has_data(symbol):
                    no_data += 1
                    self.stdout.write(f"  -> skipped (no Bronze data): {symbol}")
                    continue

                generate_and_persist_stock_analytics(stock)
                if not skip_prediction:
                    refresh_stock_prediction(stock)
                success += 1
            except Exception as exc:
                failed += 1
                self.stdout.write(f"  -> failed: {symbol} | {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                "run_analytics completed. "
                f"processed={processed}, success={success}, no_data={no_data}, failed={failed}"
            )
        )
