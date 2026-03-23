from django.conf import settings
from django.db import models
from django.utils import timezone


class Portfolio(models.Model):
    """Represents a themed group of stocks owned by a specific user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolios",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    is_default = models.BooleanField(default=False)
    portfolio_type = models.CharField(
        max_length=20,
        choices=[('default', 'Default'), ('custom', 'Custom')],
        default='custom'
    )
    geography = models.CharField(
        max_length=5,
        choices=[('IN', 'India'), ('US', 'US'), ('ALL', 'All')],
        default='ALL',
        blank=True
    )

    class Meta:
        unique_together = ("user", "name")

    def __str__(self) -> str:
        return f"{self.name} ({self.user.username})"


class Stock(models.Model):
    """Represents a stock entity tracked by the platform."""

    portfolio = models.ForeignKey(
        Portfolio,
        on_delete=models.CASCADE,
        related_name="stocks",
        null=True,
        blank=True,
    )
    symbol = models.CharField(max_length=20, unique=True)
    company_name = models.CharField(max_length=255)
    sector = models.CharField(max_length=100)
    current_price = models.FloatField()
    predicted_price_1d = models.FloatField(null=True, blank=True)
    expected_change_pct = models.FloatField(null=True, blank=True)
    direction_signal = models.CharField(max_length=30, blank=True, default="")
    model_confidence_r2 = models.FloatField(null=True, blank=True)
    prediction_status = models.CharField(max_length=30, default="unavailable")
    recommended_action = models.CharField(max_length=50, blank=True, default="")
    prediction_updated_at = models.DateTimeField(null=True, blank=True, default=timezone.now)

    # Seeding / catalogue fields
    ticker = models.CharField(max_length=30, unique=True, null=True, blank=True)
    name = models.CharField(max_length=200, null=True, blank=True)
    geography = models.CharField(
        max_length=5,
        choices=[("IN", "India"), ("US", "US")],
        default="IN",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.symbol} - {self.company_name}"


class PortfolioStock(models.Model):
    """
    Many-to-many link between Portfolio and the Stock master table.
    This is the correct way to add stocks to portfolios - never modify
    the Stock master table rows directly.
    """
    portfolio    = models.ForeignKey(
        Portfolio,
        on_delete=models.CASCADE,
        related_name='portfolio_stocks'
    )
    stock_master = models.ForeignKey(
        'StockMaster',
        on_delete=models.SET_NULL,
        related_name='portfolio_entries',
        null=True,
        blank=True,
    )
    # Denormalized fields for fast reads without joins
    ticker       = models.CharField(max_length=30, db_index=True)
    company_name = models.CharField(max_length=200, blank=True)
    sector       = models.CharField(max_length=100, blank=True)
    geography    = models.CharField(max_length=5, blank=True)
    added_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['portfolio', 'ticker']]
        ordering = ['ticker']

    def __str__(self):
        return f"{self.portfolio.name} - {self.ticker}"


class StockMaster(models.Model):
    """
    Standalone master table of all 400 approved stocks.
    Admin-managed. No FK to Portfolio.
    This is the single source of truth for all available stocks.
    """
    ticker = models.CharField(max_length=30, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    sector = models.CharField(max_length=100)
    geography = models.CharField(
        max_length=5,
        choices=[('IN', 'India'), ('US', 'US')],
        default='IN'
    )
    is_active = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['geography', 'sector', 'ticker']

    def __str__(self):
        return f"{self.ticker} - {self.name} ({self.geography})"


