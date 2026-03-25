from django.contrib.auth import get_user_model
from portfolio.models import PortfolioStock, Portfolio
from analytics.data_access import get_stocks_sentiment_bulk, get_sector_sentiment

User = get_user_model()
user = User.objects.filter(is_active=True).first()
print('user:', user)
if not user:
    raise SystemExit(0)
queryset = Portfolio.objects.filter(user=user).order_by('-is_default', 'name')
print('portfolio_count:', queryset.count())
payload = [{'id': p.id, 'geography': p.geography, 'stock_count': p.portfolio_stocks.count()} for p in queryset]
portfolio_ids = [p.id for p in queryset]
rows = list(PortfolioStock.objects.filter(portfolio_id__in=portfolio_ids).values('portfolio_id','ticker','sector'))
print('portfolio_stock_rows:', len(rows))
tickers = sorted({r['ticker'] for r in rows if r.get('ticker')})
print('ticker_count:', len(tickers))
sentiment_map = get_stocks_sentiment_bulk(tickers) if tickers else {}
print('sentiment_map_count:', len(sentiment_map))
sector_rows = get_sector_sentiment()
print('sector_rows_count:', len(sector_rows))
print('ok')
