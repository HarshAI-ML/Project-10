import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "auto_invest.settings")
django.setup()

from portfolio.models import Portfolio
deleted, _ = Portfolio.objects.filter(is_default=True).delete()
print(f"Deleted {deleted} default portfolios")
