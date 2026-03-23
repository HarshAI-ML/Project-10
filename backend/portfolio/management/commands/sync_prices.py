"""
Management command to fetch yfinance prices for portfolio stocks.
"""
import logging
import pandas as pd
import yfinance as yf
from django.core.management.base import BaseCommand
from django.db.models import Q

from portfolio.models import PortfolioStock
from pipeline.models import SilverCleanedPrice

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fetch stock prices from yfinance and save to SilverCleanedPrice'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Fetch all stocks (default: first 50)',
        )

    def handle(self, *args, **options):
        self.stdout.write("Fetching unique tickers from PortfolioStock...")
        
        # Get unique tickers from portfolio stocks
        tickers = list(
            PortfolioStock.objects.values_list('ticker', flat=True)
            .distinct()
            .order_by('ticker')
        )
        
        if not tickers:
            self.stdout.write("No stocks found in portfolios.")
            return
        
        if not options['all']:
            tickers = tickers[:50]  # Default to first 50
        
        self.stdout.write(f"[OK] Found {len(tickers)} unique tickers")
        
        self.stdout.write("\nFetching prices from yfinance...")
        count = self._fetch_prices(tickers)
        self.stdout.write(self.style.SUCCESS(f"[OK] Saved {count} price records"))
        
        self.stdout.write(self.style.SUCCESS("\n[OK] Done!"))

    def _fetch_prices(self, tickers):
        """Fetch prices and save to SilverCleanedPrice."""
        saved_count = 0
        batch_size = 30
        
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(tickers) + batch_size - 1) // batch_size
            
            self.stdout.write(f"  Batch {batch_num}/{total_batches}: fetching {len(batch)} tickers...")
            
            try:
                # Download data
                data = yf.download(
                    tickers=batch,
                    period="1y",
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    group_by="ticker",
                    threads=True
                )
                
                # Process each ticker
                for ticker in batch:
                    try:
                        if len(batch) == 1:
                            # Single ticker case
                            ticker_data = data
                        else:
                            # Multiple tickers - access by column
                            if ticker in data.columns.get_level_values('Ticker').unique():
                                ticker_data = data[ticker]
                            else:
                                self.stdout.write(f"    Warning: {ticker} not found in response")
                                continue
                        
                        # Save to database
                        for date, row in ticker_data.iterrows():
                            if pd.isna(row.get('Close')):
                                continue
                            
                            try:
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
                                saved_count += 1
                            except Exception as e:
                                logger.error(f"Error saving {ticker} for {date}: {e}")
                    
                    except Exception as e:
                        logger.error(f"Error processing {ticker}: {e}")
                        self.stdout.write(self.style.WARNING(f"    Error with {ticker}: {e}"))
            
            except Exception as e:
                logger.error(f"Error fetching batch {batch}: {e}")
                self.stdout.write(self.style.ERROR(f"  Error fetching batch: {e}"))
        
        return saved_count
