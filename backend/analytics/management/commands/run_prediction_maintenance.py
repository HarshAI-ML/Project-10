from django.core.management.base import BaseCommand

from analytics.services.price_prediction import warm_prediction_models


class Command(BaseCommand):
    help = "Warm and retrain prediction model outputs for selected stocks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            type=str,
            default="",
            help="Optional: xgboost or lstm",
        )
        parser.add_argument(
            "--symbols",
            nargs="*",
            default=[],
            help="Optional stock symbols (example: AAPL TSLA BTC-USD).",
        )

    def handle(self, *args, **options):
        model = options.get("model") or None
        symbols = options.get("symbols") or []
        report = warm_prediction_models(symbols=symbols, model=model)

        for row in report["ok"]:
            self.stdout.write(self.style.SUCCESS(f"OK: {row}"))
        for row in report["errors"]:
            self.stdout.write(self.style.WARNING(f"ERROR: {row}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Completed. success={len(report['ok'])} errors={len(report['errors'])}"
            )
        )
