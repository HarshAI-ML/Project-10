"""
Management command: populate_portfolio_stocks
Populates PortfolioStock entries for all default sector portfolios
based on sector matching from StockMaster.

Usage:
    python manage.py populate_portfolio_stocks
    python manage.py populate_portfolio_stocks --user=sunraku
    python manage.py populate_portfolio_stocks --clear
    python manage.py populate_portfolio_stocks --clear --user=sunraku
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from portfolio.models import Portfolio, PortfolioStock, StockMaster

User = get_user_model()

PORTFOLIO_SECTOR_MAP = {
    "Nifty Auto": {"sectors": ["Automobile and Auto Components"], "geography": "IN"},
    "Nifty Bank": {"sectors": ["Financial Services"], "geography": "IN"},
    "Nifty Commodities": {"sectors": ["Metals & Mining", "Chemicals"], "geography": "IN"},
    "Nifty CPSE": {"sectors": ["Oil Gas & Consumable Fuels", "Power", "Construction"], "geography": "IN"},
    "Nifty Energy": {"sectors": ["Oil Gas & Consumable Fuels", "Power"], "geography": "IN"},
    "Nifty FMCG": {"sectors": ["Fast Moving Consumer Goods"], "geography": "IN"},
    "Nifty IT": {"sectors": ["Information Technology"], "geography": "IN"},
    "Nifty Media": {"sectors": ["Consumer Services"], "geography": "IN"},
    "Nifty Metal": {"sectors": ["Metals & Mining"], "geography": "IN"},
    "Nifty MNC": {"sectors": ["Consumer Durables", "Capital Goods"], "geography": "IN"},
    "Nifty Pharma": {"sectors": ["Healthcare"], "geography": "IN"},
    "Nifty PSE": {"sectors": ["Services", "Telecommunication"], "geography": "IN"},
    "Nifty PSU Bank": {"sectors": ["Financial Services"], "geography": "IN"},
    "Nifty Realty": {"sectors": ["Realty", "Construction Materials"], "geography": "IN"},
    "US Basic Materials": {"sectors": ["Materials"], "geography": "US"},
    "US Communication Services": {"sectors": ["Communication Services"], "geography": "US"},
    "US Consumer Cyclical": {"sectors": ["Consumer Discretionary"], "geography": "US"},
    "US Consumer Defensive": {"sectors": ["Consumer Staples"], "geography": "US"},
    "US Energy": {"sectors": ["Energy"], "geography": "US"},
    "US Financial": {"sectors": ["Financial Services"], "geography": "US"},
    "US Healthcare": {"sectors": ["Healthcare"], "geography": "US"},
    "US Industrials": {"sectors": ["Industrials"], "geography": "US"},
    "US Real Estate": {"sectors": ["Real Estate"], "geography": "US"},
    "US Technology": {"sectors": ["Technology"], "geography": "US"},
    "US Utilities": {"sectors": ["Utilities"], "geography": "US"},
}


class Command(BaseCommand):
    help = "Populate PortfolioStock entries for all default sector portfolios"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=str,
            default=None,
            help="Only process this specific username. If omitted, processes all users.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            default=False,
            help="Clear existing PortfolioStock entries before repopulating.",
        )

    def handle(self, *args, **options):
        username = options["user"]
        clear = options["clear"]

        if username:
            try:
                users = [User.objects.get(username=username)]
                self.stdout.write(f"Processing single user: {username}")
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User '{username}' not found"))
                return
        else:
            users = list(User.objects.all())
            self.stdout.write(f"Processing {len(users)} users...")

        sector_stock_map = {}
        active_stocks_qs = StockMaster.objects.filter(is_active=True).exclude(ticker="")
        for stock in active_stocks_qs:
            key = (stock.sector, stock.geography)
            if key not in sector_stock_map:
                sector_stock_map[key] = []
            sector_stock_map[key].append(stock)

        self.stdout.write(f"StockMaster loaded: {active_stocks_qs.count()} active stocks")

        total_created = 0
        total_skipped = 0
        total_cleared = 0
        total_portfolios = 0

        for user in users:
            user_created = 0
            user_cleared = 0

            try:
                default_portfolios = Portfolio.objects.filter(
                    user=user,
                    is_default=True,
                    name__in=PORTFOLIO_SECTOR_MAP.keys(),
                )
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  ERROR {user.username}: failed fetching portfolios: {exc}"))
                continue

            if not default_portfolios.exists():
                self.stdout.write(f"  SKIP {user.username} — no default portfolios found")
                continue

            for portfolio in default_portfolios:
                try:
                    config = PORTFOLIO_SECTOR_MAP.get(portfolio.name)
                    if not config:
                        self.stdout.write(
                            self.style.WARNING(f"  No sector mapping for '{portfolio.name}', skipping")
                        )
                        continue

                    if clear:
                        deleted_count, _ = PortfolioStock.objects.filter(portfolio=portfolio).delete()
                        user_cleared += deleted_count
                        total_cleared += deleted_count

                    matching_stocks = []
                    for sector in config["sectors"]:
                        key = (sector, config["geography"])
                        matching_stocks.extend(sector_stock_map.get(key, []))

                    seen_tickers = set()
                    unique_stocks = []
                    for stock in matching_stocks:
                        if stock.ticker not in seen_tickers:
                            seen_tickers.add(stock.ticker)
                            unique_stocks.append(stock)

                    existing_tickers = set(
                        PortfolioStock.objects.filter(portfolio=portfolio).values_list("ticker", flat=True)
                    )

                    entries = []
                    for stock in unique_stocks:
                        if stock.ticker not in existing_tickers:
                            entries.append(
                                PortfolioStock(
                                    portfolio=portfolio,
                                    stock_master=stock,
                                    ticker=stock.ticker,
                                    company_name=stock.name,
                                    sector=stock.sector,
                                    geography=stock.geography,
                                )
                            )

                    if entries:
                        PortfolioStock.objects.bulk_create(
                            entries,
                            batch_size=200,
                            ignore_conflicts=True,
                        )
                        user_created += len(entries)
                        total_created += len(entries)
                        total_portfolios += 1
                    else:
                        total_skipped += len(unique_stocks)
                except Exception as exc:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ERROR {user.username} / {portfolio.name}: {exc}"
                        )
                    )
                    continue

            self.stdout.write(
                f"  {user.username}: "
                f"{default_portfolios.count()} portfolios | "
                f"{user_created} stocks added"
                + (f" | {user_cleared} cleared" if clear else "")
            )

        self.stdout.write("\n" + "=" * 55)
        self.stdout.write(
            self.style.SUCCESS(
                f"Done.\n"
                f"  Portfolios populated : {total_portfolios}\n"
                f"  Stocks inserted      : {total_created}\n"
                f"  Already existed      : {total_skipped}\n"
                + (f"  Entries cleared      : {total_cleared}\n" if clear else "")
            )
        )
        self.stdout.write("=" * 55)

        self.stdout.write("\nPer-portfolio stock counts (first user):")
        first_user = users[0] if users else None
        if not first_user:
            return
        for name in sorted(PORTFOLIO_SECTOR_MAP.keys()):
            p = Portfolio.objects.filter(user=first_user, name=name, is_default=True).first()
            if p:
                count = PortfolioStock.objects.filter(portfolio=p).count()
                geo = PORTFOLIO_SECTOR_MAP[name]["geography"]
                self.stdout.write(f"  [{geo}] {name}: {count} stocks")
