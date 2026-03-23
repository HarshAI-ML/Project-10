from django.contrib import admin
from .models import BronzeStockPrice, BronzeNewsArticle, PipelineRun


@admin.register(BronzeStockPrice)
class BronzeStockPriceAdmin(admin.ModelAdmin):
    list_display   = ['ticker', 'company', 'date', 'close', 'volume', 'source', 'ingested_at']
    list_filter    = ['source', 'date']
    search_fields  = ['ticker', 'company']
    ordering       = ['-date', 'ticker']


@admin.register(BronzeNewsArticle)
class BronzeNewsArticleAdmin(admin.ModelAdmin):
    list_display   = ['title', 'company_tags', 'source', 'published_at', 'ingested_at']
    list_filter    = ['source']
    search_fields  = ['title', 'company_tags']


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display    = ['run_id', 'run_type', 'status', 'stocks_total', 'stocks_success', 'stocks_failed', 'started_at']
    list_filter     = ['status', 'run_type']
    ordering        = ['-started_at']
    readonly_fields = ['run_id', 'started_at', 'completed_at']

from .models import SilverCleanedPrice

@admin.register(SilverCleanedPrice)
class SilverCleanedPriceAdmin(admin.ModelAdmin):
    list_display  = ['ticker', 'date', 'close', 'rsi_14', 'macd', 'ma_20', 'price_vs_ma20', 'processed_at']
    list_filter   = ['geography', 'sector']
    search_fields = ['ticker', 'company']
    ordering      = ['-date', 'ticker']


from pipeline.models import BronzeStockFundamentals
from pipeline.models import GoldForecastResult, GoldStockSignal


@admin.register(BronzeStockFundamentals)
class BronzeStockFundamentalsAdmin(admin.ModelAdmin):
    list_display = [
        'ticker',
        'company',
        'trailing_pe',
        'profit_margin',
        'revenue_growth',
        'market_cap',
        'beta',
        'fetched_at',
    ]
    list_filter = ['geography', 'sector']
    search_fields = ['ticker', 'company']
    ordering = ['ticker']


@admin.register(GoldStockSignal)
class GoldStockSignalAdmin(admin.ModelAdmin):
    list_display = [
        'ticker',
        'date',
        'signal',
        'confidence',
        'rsi_signal',
        'macd_signal',
        'ma_signal',
        'close',
        'rsi_14',
        'computed_at',
    ]
    list_filter = ['signal', 'rsi_signal', 'macd_signal']
    search_fields = ['ticker']
    ordering = ['-date', 'ticker']


@admin.register(GoldForecastResult)
class GoldForecastResultAdmin(admin.ModelAdmin):
    list_display = [
        'ticker',
        'forecast_date',
        'current_price',
        'predicted_price',
        'expected_change_pct',
        'direction',
        'confidence_r2',
        'model_type',
        'computed_at',
    ]
    list_filter = ['model_type', 'direction']
    search_fields = ['ticker']
    ordering = ['-forecast_date', 'ticker']
