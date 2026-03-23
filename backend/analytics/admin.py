from django.contrib import admin

from analytics.models import PredictionModelState, PredictionResultCache, StockAnalytics


@admin.register(StockAnalytics)
class StockAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "stock",
        "pe_ratio",
        "discount_level",
        "opportunity_score",
        "last_updated",
    )
    search_fields = ("stock__symbol", "stock__company_name")
    list_filter = ("discount_level", "last_updated")


@admin.register(PredictionResultCache)
class PredictionResultCacheAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "stock_symbol",
        "model_type",
        "prediction_frequency",
        "historical_period",
        "generated_at",
    )
    list_filter = ("model_type", "prediction_frequency", "historical_period")
    search_fields = ("stock_symbol",)


@admin.register(PredictionModelState)
class PredictionModelStateAdmin(admin.ModelAdmin):
    list_display = ("id", "model_type", "last_trained_at")
    search_fields = ("model_type",)
