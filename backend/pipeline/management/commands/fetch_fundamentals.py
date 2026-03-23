"""
Management command: fetch_fundamentals
Fetches PE ratio and other fundamentals from yfinance for all 400 stocks
and stores them in BronzeStockFundamentals table.

Usage:
    python manage.py fetch_fundamentals           # fetch all active stocks
    python manage.py fetch_fundamentals --ticker RELIANCE.NS   # single stock
    python manage.py fetch_fundamentals --refresh  # re-fetch even if data exists
"""
import logging

from django.core.management.base import BaseCommand

from pipeline.fetchers.yfinance_fetcher import fetch_fundamentals_batch, fetch_fundamentals_for_ticker
from pipeline.models import BronzeStockFundamentals
from portfolio.models import StockMaster

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fetch fundamentals (PE, EPS, margins etc.) from yfinance and store in DB"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ticker",
            type=str,
            default=None,
            help="Fetch only this ticker. If omitted fetches all active stocks.",
        )
        parser.add_argument(
            "--refresh",
            action="store_true",
            default=False,
            help="Re-fetch even if fundamentals already exist for this ticker.",
        )

    def handle(self, *args, **options):
        single_ticker = options["ticker"]
        refresh = options["refresh"]

        if single_ticker:
            tickers = [single_ticker]
            self.stdout.write(f"Fetching fundamentals for: {single_ticker}")
        else:
            stocks = (
                StockMaster.objects.filter(is_active=True)
                .exclude(ticker__isnull=True)
                .exclude(ticker="")
            )

            if not refresh:
                existing = set(
                    BronzeStockFundamentals.objects.values_list("ticker", flat=True).distinct()
                )
                all_tickers = list(stocks.values_list("ticker", flat=True))
                tickers = [t for t in all_tickers if t not in existing]
                self.stdout.write(
                    f"Total active stocks : {len(all_tickers)}\n"
                    f"Already have data   : {len(existing)}\n"
                    f"To fetch            : {len(tickers)}"
                )
            else:
                tickers = list(stocks.values_list("ticker", flat=True))
                self.stdout.write(f"Refreshing all {len(tickers)} stocks...")

        if not tickers:
            self.stdout.write(
                self.style.SUCCESS("All stocks already have fundamentals. Use --refresh to re-fetch.")
            )
            return

        stock_meta = {
            s.ticker: {
                "company": s.name,
                "sector": s.sector,
                "geography": s.geography,
            }
            for s in StockMaster.objects.filter(ticker__in=tickers)
        }

        self.stdout.write(f"\nStarting fundamentals fetch for {len(tickers)} stocks...")
        self.stdout.write("This may take several minutes - fetching in batches of 10.\n")

        if single_ticker:
            results = {single_ticker: fetch_fundamentals_for_ticker(single_ticker)}
        else:
            results = fetch_fundamentals_batch(tickers)

        created = 0
        empty = 0
        errors = 0

        for ticker, data in results.items():
            if not data:
                empty += 1
                self.stdout.write(self.style.WARNING(f"  NO DATA: {ticker}"))
                continue

            try:
                meta = stock_meta.get(ticker, {})
                BronzeStockFundamentals.objects.create(
                    ticker=ticker,
                    company=meta.get("company", ""),
                    sector=meta.get("sector", ""),
                    geography=meta.get("geography", ""),
                    trailing_pe=data.get("trailing_pe"),
                    forward_pe=data.get("forward_pe"),
                    price_to_book=data.get("price_to_book"),
                    price_to_sales=data.get("price_to_sales"),
                    enterprise_value=data.get("enterprise_value"),
                    ev_to_ebitda=data.get("ev_to_ebitda"),
                    profit_margin=data.get("profit_margin"),
                    operating_margin=data.get("operating_margin"),
                    gross_margin=data.get("gross_margin"),
                    return_on_equity=data.get("return_on_equity"),
                    return_on_assets=data.get("return_on_assets"),
                    revenue_growth=data.get("revenue_growth"),
                    earnings_growth=data.get("earnings_growth"),
                    eps_trailing=data.get("eps_trailing"),
                    eps_forward=data.get("eps_forward"),
                    market_cap=data.get("market_cap"),
                    total_revenue=data.get("total_revenue"),
                    free_cashflow=data.get("free_cashflow"),
                    debt_to_equity=data.get("debt_to_equity"),
                    current_ratio=data.get("current_ratio"),
                    beta=data.get("beta"),
                    week52_high=data.get("week52_high"),
                    week52_low=data.get("week52_low"),
                    dividend_yield=data.get("dividend_yield"),
                )
                created += 1
                pe = data.get("trailing_pe")
                self.stdout.write(f"  OK {ticker} | PE={pe}")

            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f"  DB ERROR {ticker}: {e}"))

        self.stdout.write(f"\n{'='*50}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done.\n"
                f"  Fetched successfully : {created}\n"
                f"  No data returned    : {empty}\n"
                f"  DB errors           : {errors}\n"
                f"  Total processed     : {len(tickers)}"
            )
        )
        self.stdout.write(f"{'='*50}")

        total_in_db = BronzeStockFundamentals.objects.values("ticker").distinct().count()
        with_pe = (
            BronzeStockFundamentals.objects.exclude(trailing_pe__isnull=True)
            .values("ticker")
            .distinct()
            .count()
        )
        self.stdout.write("\nDB verification:")
        self.stdout.write(f"  Tickers in BronzeStockFundamentals : {total_in_db}")
        self.stdout.write(f"  Tickers with PE ratio              : {with_pe}")
