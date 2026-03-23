from django.contrib import admin

from portfolio.models import Portfolio, PortfolioStock, Stock, StockMaster


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "description")
    search_fields = ("name",)


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("id", "symbol", "company_name", "portfolio", "sector", "current_price")
    search_fields = ("symbol", "company_name", "sector", "portfolio__name")
    list_filter = ("sector", "portfolio")

@admin.register(PortfolioStock)
class PortfolioStockAdmin(admin.ModelAdmin):
    list_display  = ['portfolio', 'ticker', 'company_name', 'sector', 'geography', 'added_at']
    list_filter   = ['geography', 'sector']
    search_fields = ['ticker', 'company_name', 'portfolio__name']
    ordering      = ['portfolio', 'ticker']


@admin.register(StockMaster)
class StockMasterAdmin(admin.ModelAdmin):
    list_display = ['ticker', 'name', 'sector', 'geography', 'is_active', 'added_at']
    list_filter = ['geography', 'sector', 'is_active']
    search_fields = ['ticker', 'name']
    ordering = ['geography', 'sector', 'ticker']
    list_per_page = 50
