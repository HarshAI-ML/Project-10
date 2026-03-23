#!/usr/bin/env python
"""Populate forecast and signal data with defaults"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auto_invest.settings')
sys.path.insert(0, os.path.dirname(__file__))

django.setup()

from datetime import date
from portfolio.models import PortfolioStock
from pipeline.models import SilverCleanedPrice, GoldForecastResult, GoldStockSignal

def populate_forecasts():
    """Create forecast records with defaults for all tickers"""
    print("\n=== Creating Forecast Records ===")
    
    tickers = list(PortfolioStock.objects.values_list('ticker', flat=True).distinct())
    
    # Get existing
    existing = set(GoldForecastResult.objects.values_list('ticker', flat=True).distinct())
    missing = [t for t in tickers if t not in existing]
    
    if not missing:
        print("[OK] All forecasts exist")
        return
    
    print(f"Creating forecasts for {len(missing)} tickers...")
    
    created = 0
    for ticker in missing:
        try:
            # Get latest price
            latest = SilverCleanedPrice.objects.filter(ticker=ticker).order_by('-date').first()
            if not latest:
                continue
            
            current_price = latest.close
            
            # Calculate simple forecast (no change)
            predicted_price = current_price
            expected_change = 0.0
            direction = "Hold"
            confidence = 0.50
            
            GoldForecastResult.objects.create(
                ticker=ticker,
                current_price=current_price,
                predicted_price=predicted_price,
                expected_change_pct=expected_change,
                direction=direction,
                confidence_r2=confidence,
                model_type='default',
                forecast_date=date.today()
            )
            
            created += 1
            if created % 50 == 0:
                print(f"  Created {created} forecasts...")
        
        except Exception as e:
            print(f"  Error {ticker}: {e}")
    
    print(f"[OK] Created {created} forecast records")


def populate_signals():
    """Create signal records with defaults for all tickers"""
    print("\n=== Creating Signal Records ===")
    
    tickers = list(PortfolioStock.objects.values_list('ticker', flat=True).distinct())
    
    # Get existing
    existing = set(GoldStockSignal.objects.values_list('ticker', flat=True).distinct())
    missing = [t for t in tickers if t not in existing]
    
    if not missing:
        print("[OK] All signals exist")
        return
    
    print(f"Creating signals for {len(missing)} tickers...")
    
    created = 0
    for ticker in missing:
        try:
            # Get latest price data
            latest = SilverCleanedPrice.objects.filter(ticker=ticker).order_by('-date').first()
            if not latest:
                continue
            
            close_price = latest.close
            rsi = latest.rsi_14 or 50
            
            # Default signal: neutral
            signal = "Hold"
            confidence = 0.50
            
            GoldStockSignal.objects.create(
                ticker=ticker,
                signal=signal,
                confidence=confidence,
                rsi_signal="Neutral",
                macd_signal="Neutral",
                ma_signal="Neutral",
                rsi_14=rsi,
                close=close_price,
                date=date.today()
            )
            
            created += 1
            if created % 50 == 0:
                print(f"  Created {created} signals...")
        
        except Exception as e:
            print(f"  Error {ticker}: {e}")
    
    print(f"[OK] Created {created} signal records")


if __name__ == '__main__':
    try:
        populate_forecasts()
        populate_signals()
        print("\n[OK] All forecast and signal data populated!")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
