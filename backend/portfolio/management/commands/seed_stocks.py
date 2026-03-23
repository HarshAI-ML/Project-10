import sys
import time

from django.core.management.base import BaseCommand

from portfolio.models import Stock
from scripts.nifty500_top200 import ALL_STOCKS


class Command(BaseCommand):
    help = "Seed the database with 400 pre-defined stocks (200 Indian Nifty 200 + 200 US S&P 500)"

    def handle(self, *args, **options):
        created_count = 0
        skipped_count = 0
        error_count = 0

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Seeding {len(ALL_STOCKS)} stocks into portfolio_stock ...\n"
        ))

        for ticker, name, sector, geography in ALL_STOCKS:
            try:
                stock, created = Stock.objects.update_or_create(
                    symbol=ticker,
                    defaults={
                        "ticker":        ticker,
                        "name":          name,
                        "company_name":  name,
                        "sector":        sector,
                        "geography":     geography,
                        "is_active":     True,
                        # Only set current_price when creating (don't overwrite live prices)
                    },
                )
                if created:
                    # Set required field only on new rows
                    stock.current_price = 0.0
                    stock.save(update_fields=["current_price"])
                    created_count += 1
                    self.stdout.write(f"  Created : {ticker}")
                else:
                    skipped_count += 1
                    self.stdout.write(f"  Exists  : {ticker}")
            except Exception as exc:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"  ERROR   : {ticker} -> {exc}")
                )

        total = created_count + skipped_count
        self.stdout.write("\n" + "─" * 50)
        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {created_count}, Skipped {skipped_count}, "
            f"Errors {error_count}, Total {total}"
        ))
