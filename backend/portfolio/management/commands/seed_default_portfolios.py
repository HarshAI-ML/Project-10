from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from portfolio.services import create_default_portfolios_for_user, user_has_default_portfolios

User = get_user_model()

class Command(BaseCommand):
    help = 'Create default sector portfolios for all existing users who do not have them yet'

    def handle(self, *args, **options):
        users = User.objects.all()
        self.stdout.write(f"Processing {users.count()} users...")

        for user in users:
            if user_has_default_portfolios(user):
                self.stdout.write(f"  SKIP {user.username} — already has defaults")
                continue

            result = create_default_portfolios_for_user(user)
            self.stdout.write(
                f"  DONE {user.username} — "
                f"{result['created']} portfolios, "
                f"{result['total_stocks']} stocks"
            )

        self.stdout.write(self.style.SUCCESS("All users processed."))
