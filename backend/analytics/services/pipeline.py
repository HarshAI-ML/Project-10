from __future__ import annotations

from django.utils import timezone

from analytics.models import StockAnalytics
from analytics.services.clean_data import clean_data
from analytics.services.fetch_data import fetch_data
from analytics.services.indicators import indicators
from analytics.services.opportunity_engine import opportunity_engine
from analytics.services.plot_data import plot_data
from portfolio.models import Stock


def generate_and_persist_stock_analytics(stock: Stock) -> StockAnalytics:
    """
    Generate analytics for one stock and persist to StockAnalytics table.
    Also refreshes Stock.current_price with the latest close from yfinance.
    """
    raw_df = fetch_data(stock.symbol)
    cleaned_df = clean_data(raw_df)
    indicator_data = indicators(cleaned_df, stock.symbol)
    score = opportunity_engine(
        pe_ratio=indicator_data["pe_ratio"],
        discount_level=indicator_data["discount_level"],
    )
    graph_json = plot_data(cleaned_df)

    analytics, _ = StockAnalytics.objects.update_or_create(
        stock=stock,
        defaults={
            "pe_ratio": indicator_data["pe_ratio"],
            "discount_level": indicator_data["discount_level"],
            "opportunity_score": score,
            "graph_data": graph_json,
            "last_updated": timezone.now(),
        },
    )

    # Keep Stock.current_price in sync with the latest close price
    # so the frontend always shows a consistent value without live fetches
    if cleaned_df:
        latest_close = round(float(cleaned_df[-1]["close"]), 2)
        if stock.current_price != latest_close:
            stock.current_price = latest_close
            stock.save(update_fields=["current_price"])

    return analytics
