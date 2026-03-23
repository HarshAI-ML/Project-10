"""
Management command to populate Stock prices by fetching from yfinance
and create initial analytics data.
"""
import logging
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from django.core.management.base import BaseCommand
from django.utils import timezone

from portfolio.models import Stock
from analytics.models import StockAnalytics
from pipeline.models import SilverCleanedPrice

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fetch initial stock prices from yfinance and populate database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Number of stocks to fetch (default: 50)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Fetch all stocks',
        )

    def handle(self, *args, **options):
        limit = None if options['all'] else options['limit']
        
        self.stdout.write("Step 1: Fetching stock prices from yfinance...")
        price_count = self._fetch_and_save_prices(limit)
        self.stdout.write(self.style.SUCCESS(f"[OK] Fetched and saved {price_count} stock price records"))

        self.stdout.write("\nStep 2: Populating Stock current_price...")
        updated_count = self._populate_current_prices()
        self.stdout.write(self.style.SUCCESS(f"[OK] Updated {updated_count} stocks with current prices"))

        self.stdout.write("\nStep 3: Creating StockAnalytics...")
        analytics_count = self._create_analytics()
        self.stdout.write(self.style.SUCCESS(f"[OK] Created {analytics_count} analytics records"))

        self.stdout.write(self.style.SUCCESS("\n[OK] All done!"))

    def _fetch_and_save_prices(self, limit=None):
        """Fetch prices from yfinance and save to SilverCleanedPrice."""
        stocks = Stock.objects.all()
        if limit:
            stocks = stocks[:limit]
        
        tickers = [s.symbol for s in stocks]
        self.stdout.write(f"Fetching {len(tickers)} stocks...")
        
        saved_count = 0
        
        # Fetch in batches
        batch_size = 50
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            self.stdout.write(f"  Batch {i//batch_size + 1}: fetching {len(batch)} tickers...")
            
            try:
                # Fetch last 30 days
                data = yf.download(
                    tickers=batch,
                    period="30d",
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    group_by="ticker",
                    threads=True
                )
                
                # Handle single ticker case
                if isinstance(data.columns, list):
                    # Multiple tickers
                    for ticker in batch:
                        if ticker in data.columns.get_level_values(1).unique():
                            self._save_ticker_data(ticker, data[ticker])
                            saved_count += 1
                else:
                    # Single ticker
                    ticker = batch[0]
                    self._save_ticker_data(ticker, data)
                    saved_count += 1
                    
            except Exception as e:
                logger.error(f"Error fetching batch {batch}: {e}")
                self.stdout.write(self.style.ERROR(f"  Error: {e}"))
        
        return saved_count

    def _save_ticker_data(self, ticker, df):
        """Save price data for a single ticker."""
        try:
            stock = Stock.objects.get(symbol=ticker)
            
            for date, row in df.iterrows():
                if pd.isna(row['Close']):
                    continue
                
                SilverCleanedPrice.objects.get_or_create(
                    ticker=ticker,
                    date=date.date(),
                    defaults={
                        'company': stock.company_name,
                        'sector': stock.sector,
                        'geography': stock.geography,
                        'open': row.get('Open'),
                        'high': row.get('High'),
                        'low': row.get('Low'),
                        'close': row['Close'],
                        'volume': row.get('Volume'),
                    }
                )
        except Exception as e:
            logger.error(f"Error saving data for {ticker}: {e}")

    def _populate_current_prices(self):
        """Update Stock.current_price from latest SilverCleanedPrice."""
        updated_count = 0
        
        stocks = Stock.objects.all()
        for stock in stocks:
            latest_price = SilverCleanedPrice.objects.filter(
                ticker=stock.symbol
            ).order_by('-date').values_list('close', flat=True).first()
            
            if latest_price:
                stock.current_price = latest_price
                stock.save(update_fields=['current_price'])
                updated_count += 1
        
        return updated_count

    def _create_analytics(self):
        """Create StockAnalytics for stocks if missing."""
        created_count = 0
        
        stocks = Stock.objects.filter(analytics__isnull=True)
        
        for stock in stocks:
            try:
                prices = SilverCleanedPrice.objects.filter(
                    ticker=stock.symbol
                ).order_by('date').values_list('close', flat=True)
                
                if not prices:
                    continue
                
                graph_data = {
                    'price': [float(p) for p in prices],
                    'count': len(prices),
                }
                
                StockAnalytics.objects.create(
                    stock=stock,
                    pe_ratio=0.0,
                    discount_level='Low Data',
                    opportunity_score=0.0,
                    graph_data=graph_data,
                )
                created_count += 1
            except Exception as e:
                logger.error(f"Error creating analytics for {stock.symbol}: {e}")
        
        return created_count
