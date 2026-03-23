import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auto_invest.settings')
django.setup()

from portfolio.models import PortfolioStock
from pipeline.models import SilverCleanedPrice
from analytics.models import StockAnalytics

# Check portfolio stocks
total_portfolio_stocks = PortfolioStock.objects.count()
print(f"Total PortfolioStock records: {total_portfolio_stocks}")

# Check which ones have price data
tickers_with_portfolio_stocks = list(PortfolioStock.objects.values_list('ticker', flat=True).distinct())
print(f"Unique tickers in portfolios: {len(tickers_with_portfolio_stocks)}")

# Check silver cleaned price
tickers_with_prices = list(SilverCleanedPrice.objects.values_list('ticker', flat=True).distinct())
print(f"Tickers with SilverCleanedPrice data: {len(tickers_with_prices)}")

# Find missing tickers
missing_tickers = set(tickers_with_portfolio_stocks) - set(tickers_with_prices)
print(f"\nMissing tickers (no prices): {len(missing_tickers)}")
print(f"Sample missing: {sorted(list(missing_tickers))[:10]}")

# Check sample of tickers that have prices
if tickers_with_prices:
    sample_ticker = tickers_with_prices[0]
    price_count = SilverCleanedPrice.objects.filter(ticker=sample_ticker).count()
    latest_price = SilverCleanedPrice.objects.filter(ticker=sample_ticker).latest('date')
    print(f"\nSample ticker: {sample_ticker}")
    print(f"  Price records: {price_count}")
    print(f"  Latest: {latest_price.date} = {latest_price.close}")

# Check analytics
analytics_count = StockAnalytics.objects.count()
print(f"\nStockAnalytics records: {analytics_count}")
