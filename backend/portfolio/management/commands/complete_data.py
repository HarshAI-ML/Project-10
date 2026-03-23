"""
Management command to complete data population:
1. Fetch remaining missing ticker prices
2. Create StockAnalytics for all stocks
"""
import logging
import pandas as pd
import yfinance as yf
import traceback
from django.core.management.base import BaseCommand
from django.db.models import Max

from portfolio.models import PortfolioStock, Stock
from pipeline.models import SilverCleanedPrice
from analytics.models import StockAnalytics

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Complete data population: fetch missing prices and create analytics'

    def handle(self, *args, **options):
        self.stdout.write("\n=== Step 1: Fetching missing ticker prices ===")
        self._fetch_missing_prices()

        self.stdout.write("\n=== Step 2: Creating StockAnalytics ===")
        self._create_stock_analytics()

        self.stdout.write(self.style.SUCCESS("\n[OK] All done!"))

    def _fetch_missing_prices(self):
        """Fetch prices for tickers with no SilverCleanedPrice data."""
        # Get all tickers in portfolios
        all_tickers = list(
            PortfolioStock.objects.values_list('ticker', flat=True)
            .distinct()
            .order_by('ticker')
        )
        
        # Get tickers with prices
        tickers_with_prices = set(
            SilverCleanedPrice.objects.values_list('ticker', flat=True).distinct()
        )
        
        # Find missing
        missing_tickers = [t for t in all_tickers if t not in tickers_with_prices]
        
        if not missing_tickers:
            self.stdout.write("[OK] All tickers have price data")
            return
        
        self.stdout.write(f"Fetching {len(missing_tickers)} missing tickers...")
        
        batch_size = 20
        successful = 0
        failed = 0
        
        for i in range(0, len(missing_tickers), batch_size):
            batch = missing_tickers[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(missing_tickers) + batch_size - 1) // batch_size
            
            self.stdout.write(f"  Batch {batch_num}/{total_batches}: {batch}")
            
            try:
                data = yf.download(
                    tickers=batch,
                    period="1y",
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    group_by="ticker",
                    threads=True
                )
                
                # Save to database
                for ticker in batch:
                    try:
                        if len(batch) == 1:
                            ticker_data = data
                        else:
                            if ticker not in data.columns.get_level_values('Ticker').unique():
                                self.stdout.write(f"    Skip: {ticker} not in yfinance")
                                continue
                            ticker_data = data[ticker]
                        
                        saved = 0
                        for date, row in ticker_data.iterrows():
                            if pd.isna(row.get('Close')):
                                continue
                            
                            SilverCleanedPrice.objects.update_or_create(
                                ticker=ticker,
                                date=pd.Timestamp(date).date(),
                                defaults={
                                    'open': float(row.get('Open', 0)),
                                    'high': float(row.get('High', 0)),
                                    'low': float(row.get('Low', 0)),
                                    'close': float(row['Close']),
                                    'volume': int(row.get('Volume', 0)) if not pd.isna(row.get('Volume')) else 0,
                                }
                            )
                            saved += 1
                        
                        if saved > 0:
                            successful += 1
                            self.stdout.write(f"    [OK] {ticker}: {saved} prices")
                        else:
                            failed += 1
                    
                    except Exception as e:
                        failed += 1
                        logger.error(f"Error with {ticker}: {e}")
                        self.stdout.write(f"    [ERROR] {ticker}: {e}")
            
            except Exception as e:
                failed += len(batch)
                logger.error(f"Batch error: {e}")
                self.stdout.write(self.style.ERROR(f"  Batch error: {e}"))
        
        self.stdout.write(self.style.SUCCESS(f"[OK] Fetched prices for {successful} tickers, {failed} failed"))

    def _create_stock_analytics(self):
        """Create StockAnalytics records for all portfolio stocks."""
        # Get all portfolio stocks
        portfolio_stocks = PortfolioStock.objects.values_list('ticker', flat=True).distinct()
        
        # Get with existing analytics
        existing = set(
            StockAnalytics.objects.filter(
                stock__symbol__in=portfolio_stocks
            ).values_list('stock__symbol', flat=True)
        )
        
        # Get missing analytics
        missing_tickers = [t for t in portfolio_stocks if t not in existing]
        
        if not missing_tickers:
            self.stdout.write("[OK] All stocks have analytics")
            return
        
        self.stdout.write(f"Creating analytics for {len(missing_tickers)} stocks...")
        
        created = 0
        failed = 0
        
        for ticker in missing_tickers:
            try:
                # Get or create Stock object
                stock, _ = Stock.objects.get_or_create(
                    symbol=ticker,
                    defaults={'company_name': ticker, 'current_price': 0}
                )
                
                # Get price data
                prices = SilverCleanedPrice.objects.filter(
                    ticker=ticker
                ).order_by('date').values_list('close', 'high', 'low', 'date')
                
                if not prices:
                    failed += 1
                    continue
                
                prices_list = list(prices)
                closes = [float(p[0]) for p in prices_list]
                dates = [p[3] for p in prices_list]
                
                # Create graph data
                graph_data = {
                    'price': closes,
                    'count': len(closes),
                    'min_date': str(dates[0]) if dates else None,
                    'max_date': str(dates[-1]) if dates else None,
                }
                
                # Get latest close price
                latest_close = closes[-1] if closes else 0
                stock.current_price = latest_close
                stock.save()
                
                # Create analytics
                StockAnalytics.objects.get_or_create(
                    stock=stock,
                    defaults={
                        'pe_ratio': 0.0,
                        'discount_level': 'Low Data',
                        'opportunity_score': 0.0,
                        'graph_data': graph_data,
                    }
                )
                
                created += 1
                if created % 50 == 0:
                    self.stdout.write(f"  Created {created} analytics...")
            
            except Exception as e:
                failed += 1
                logger.error(f"Error creating analytics for {ticker}: {e}")
        
        self.stdout.write(self.style.SUCCESS(f"[OK] Created {created} analytics, {failed} failed"))
