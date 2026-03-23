from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from pipeline.models import BronzeNewsArticle, BronzeStockFundamentals, GoldForecastResult, GoldStockSignal
from portfolio.models import Portfolio, PortfolioStock, StockMaster


class Command(BaseCommand):
    help = (
        "One-shot bootstrap for local/dev data: migrate, seed stocks, create defaults, "
        "populate portfolio holdings, fetch fundamentals, and run full pipeline."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-fundamentals",
            action="store_true",
            default=False,
            help="Skip fetch_fundamentals step (faster bootstrap).",
        )
        parser.add_argument(
            "--refresh-fundamentals",
            action="store_true",
            default=False,
            help="Pass --refresh to fetch_fundamentals.",
        )
        parser.add_argument(
            "--no-clear-portfolio-stocks",
            action="store_true",
            default=False,
            help="Do not clear existing PortfolioStock rows before repopulating.",
        )

    def _run_step(self, title: str, fn):
        self.stdout.write(f"\n[{title}]")
        fn()
        self.stdout.write(self.style.SUCCESS(f"{title}: done"))

    def handle(self, *args, **options):
        skip_fundamentals = options["skip_fundamentals"]
        refresh_fundamentals = options["refresh_fundamentals"]
        no_clear_portfolio_stocks = options["no_clear_portfolio_stocks"]

        self.stdout.write(self.style.SUCCESS("Starting one-shot bootstrap..."))

        self._run_step("1/6 migrate", lambda: call_command("migrate"))
        self._run_step("2/6 seed_stock_master", lambda: call_command("seed_stock_master"))
        self._run_step("3/6 seed_default_portfolios", lambda: call_command("seed_default_portfolios"))

        if no_clear_portfolio_stocks:
            self._run_step(
                "4/6 populate_portfolio_stocks",
                lambda: call_command("populate_portfolio_stocks"),
            )
        else:
            self._run_step(
                "4/6 populate_portfolio_stocks --clear",
                lambda: call_command("populate_portfolio_stocks", clear=True),
            )

        if skip_fundamentals:
            self.stdout.write("\n[5/6 fetch_fundamentals]")
            self.stdout.write("Skipped (--skip-fundamentals)")
        else:
            if refresh_fundamentals:
                self._run_step(
                    "5/6 fetch_fundamentals --refresh",
                    lambda: call_command("fetch_fundamentals", refresh=True),
                )
            else:
                self._run_step("5/6 fetch_fundamentals", lambda: call_command("fetch_fundamentals"))

        self._run_step("6/6 run_pipeline --mode=all", lambda: call_command("run_pipeline", mode="all"))

        # Final verification summary
        User = get_user_model()
        user_count = User.objects.count()
        default_portfolios = Portfolio.objects.filter(is_default=True).count()
        portfolio_stocks = PortfolioStock.objects.count()
        stock_master = StockMaster.objects.count()
        fundamentals = BronzeStockFundamentals.objects.values("ticker").distinct().count()
        gold_signals = GoldStockSignal.objects.count()
        gold_forecasts = GoldForecastResult.objects.count()
        news_articles = BronzeNewsArticle.objects.count()

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Bootstrap completed successfully."))
        self.stdout.write(f"Users                          : {user_count}")
        self.stdout.write(f"StockMaster                    : {stock_master}")
        self.stdout.write(f"Default portfolios (all users) : {default_portfolios}")
        self.stdout.write(f"PortfolioStock rows            : {portfolio_stocks}")
        self.stdout.write(f"Fundamentals tickers           : {fundamentals}")
        self.stdout.write(f"GoldStockSignal rows           : {gold_signals}")
        self.stdout.write(f"GoldForecastResult rows        : {gold_forecasts}")
        self.stdout.write(f"BronzeNewsArticle rows         : {news_articles}")
        self.stdout.write("=" * 60)
        self.stdout.write(
            "\nNext: start backend + frontend and open a portfolio to see predictions/signals."
        )
