from django.core.management.base import BaseCommand

from portfolio.models import StockMaster
from scripts.nifty500_top200 import ALL_STOCKS


class Command(BaseCommand):
    help = "Seed the StockMaster table with all 400 stocks from scripts/nifty500_top200.py"

    def handle(self, *args, **options):
        self.stdout.write(f"Seeding {len(ALL_STOCKS)} stocks into StockMaster...")

        created = 0
        updated = 0
        errors = 0

        for ticker, name, sector, geography in ALL_STOCKS:
            try:
                _, was_created = StockMaster.objects.update_or_create(
                    ticker=ticker,
                    defaults={
                        "name": name,
                        "sector": sector,
                        "geography": geography,
                        "is_active": True,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as exc:
                errors += 1
                self.stdout.write(self.style.ERROR(f"  ERROR {ticker}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Created: {created} | Updated: {updated} | Errors: {errors} | Total: {created + updated}"
            )
        )

        total = StockMaster.objects.count()
        indian = StockMaster.objects.filter(geography="IN").count()
        us = StockMaster.objects.filter(geography="US").count()
        self.stdout.write(f"StockMaster totals: {total} stocks ({indian} IN + {us} US)")
