"""
Management command to populate Stock objects with price data and analytics
from pipeline and analytics tables.
"""
import logging
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db.models import Max, Min

from portfolio.models import Stock, StockMaster
from analytics.models import StockAnalytics
from pipeline.models import SilverCleanedPrice

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Populate Stock prices and analytics from pipeline data'

    def handle(self, *args, **options):
        self.stdout.write("Step 1: Populating Stock current prices from SilverCleanedPrice...")
        price_count = self._populate_prices()
        self.stdout.write(self.style.SUCCESS(f"[OK] Updated {price_count} stocks with current prices"))

        self.stdout.write("\nStep 2: Creating StockAnalytics records...")
        analytics_count = self._create_analytics()
        self.stdout.write(self.style.SUCCESS(f"[OK] Created {analytics_count} analytics records"))

        self.stdout.write(self.style.SUCCESS("\n[OK] All done!"))

    def _populate_prices(self):
        """Update Stock.current_price from latest SilverCleanedPrice."""
        updated_count = 0
        
        # Get latest price for each ticker
        latest_prices = SilverCleanedPrice.objects.values('ticker').annotate(
            latest_close=Max('close'),
            latest_date=Max('date')
        )
        
        for price_data in latest_prices:
            ticker = price_data['ticker']
            close = price_data['latest_close']
            
            try:
                stock = Stock.objects.get(symbol=ticker)
                if stock.current_price != close:
                    stock.current_price = close
                    stock.save(update_fields=['current_price'])
                    updated_count += 1
            except Stock.DoesNotExist:
                logger.warning(f"Stock not found for ticker: {ticker}")
        
        return updated_count

    def _create_analytics(self):
        """Create StockAnalytics for stocks if they don't exist."""
        created_count = 0
        
        stocks = Stock.objects.filter(analytics__isnull=True)[:100]  # Process in batches
        
        for stock in stocks:
            try:
                # Get price history for this stock
                prices = SilverCleanedPrice.objects.filter(
                    ticker=stock.symbol
                ).values_list('close', flat=True).order_by('date')
                
                if not prices:
                    continue
                
                graph_data = {
                    'price': [float(p) for p in prices],
                    'count': len(prices),
                }
                
                # Create placeholder analytics
                StockAnalytics.objects.get_or_create(
                    stock=stock,
                    defaults={
                        'pe_ratio': 0.0,
                        'discount_level': 'Low Data',
                        'opportunity_score': 0.0,
                        'graph_data': graph_data,
                    }
                )
                created_count += 1
            except Exception as e:
                logger.error(f"Error creating analytics for {stock.symbol}: {e}")
        
        return created_count
