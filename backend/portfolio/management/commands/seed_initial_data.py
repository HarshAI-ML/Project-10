from django.core.management.base import BaseCommand

from portfolio.models import Portfolio


class Command(BaseCommand):
    help = "Seed default portfolios only. Stocks are user-managed via API."

    PORTFOLIOS = [
        ("Automobile", "Automobile sector portfolio."),
        ("Healthcare", "Healthcare and pharma sector portfolio."),
    ]

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for name, description in self.PORTFOLIOS:
            portfolio, created = Portfolio.objects.get_or_create(
                name=name,
                defaults={"description": description},
            )
            if created:
                created_count += 1
            elif portfolio.description != description:
                portfolio.description = description
                portfolio.save(update_fields=["description"])
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Portfolio seed complete. Created: {created_count}, updated: {updated_count}."
            )
        )
