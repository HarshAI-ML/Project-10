from django.db import models
from django.utils import timezone

from portfolio.models import Stock


class StockAnalytics(models.Model):
    """Precomputed analytics for a single stock."""

    stock = models.OneToOneField(
        Stock,
        on_delete=models.CASCADE,
        related_name="analytics",
    )
    pe_ratio = models.FloatField()
    discount_level = models.CharField(max_length=50)
    opportunity_score = models.FloatField()
    graph_data = models.JSONField(default=dict)
    last_updated = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"Analytics({self.stock.symbol})"


class PredictionResultCache(models.Model):
    """Cached prediction output for a specific request signature."""

    stock_symbol = models.CharField(max_length=20, db_index=True)
    model_type = models.CharField(max_length=20, db_index=True)
    prediction_frequency = models.CharField(max_length=20, db_index=True)
    historical_period = models.CharField(max_length=20, db_index=True)
    generated_at = models.DateTimeField(default=timezone.now, db_index=True)
    forecast_data = models.JSONField(default=dict)
    plots_path = models.JSONField(default=dict)

    class Meta:
        unique_together = (
            "stock_symbol",
            "model_type",
            "prediction_frequency",
            "historical_period",
        )

    def __str__(self) -> str:
        return (
            f"PredictionCache({self.stock_symbol}, {self.model_type}, "
            f"{self.prediction_frequency}, {self.historical_period})"
        )


class PredictionModelState(models.Model):
    """Tracks model freshness to support scheduled retraining cadence."""

    model_type = models.CharField(max_length=20, unique=True)
    last_trained_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"PredictionModelState({self.model_type})"
