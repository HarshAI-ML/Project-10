import logging
import time
import uuid
from typing import List, Optional
from datetime import timezone as dt_timezone

import pandas as pd
import yfinance as yf
from django.utils import timezone

from pipeline.models import BronzeStockPrice

logger = logging.getLogger(__name__)

class YFinanceBatchFetcher:
    """
    Handles robust fetching from yfinance using batches to respect rate limits.
    Writes entirely to BronzeStockPrice — append only, never deletes/updates old rows.
    """
    
    def __init__(self, batch_size=50, sleep_time=2.0):
        self.batch_size = batch_size
        self.sleep_time = sleep_time
        
    def fetch_prices(self, tickers: List[str], period="1d", interval="1d") -> None:
        """
        Fetch OHLCV for the given tickers and insert into BronzeStockPrice.
        """
        if not tickers:
            return
        self.fetch_run_id = uuid.uuid4().hex
            
        logger.info(f"YFinanceBatchFetcher: Fetching {len(tickers)} tickers. Period={period}, Interval={interval}")
        
        for i in range(0, len(tickers), self.batch_size):
            batch = tickers[i:i + self.batch_size]
            logger.info(f"Processing batch {i//self.batch_size + 1}: {len(batch)} tickers")
            self._process_batch(batch, period, interval)
            time.sleep(self.sleep_time)

    def _process_batch(self, batch: List[str], period: str, interval: str):
        try:
            # yfinance returns a MultiIndex column DataFrame when given multiple tickers
            df = yf.download(
                tickers=batch,
                period=period,
                interval=interval,
                auto_adjust=True,
                group_by="ticker",
                threads=True,
                progress=False
            )
        except Exception as e:
            logger.error(f"yfinance download failed for batch: {e}")
            return
            
        if df is None or df.empty:
            logger.warning("Empty dataframe returned from yfinance")
            return
            
        # Standardize MultiIndex handling
        if len(batch) == 1:
            # Single ticker case: yf doesn't use MultiIndex
            self._save_ticker_data(batch[0], df)
        else:
            # Multi-ticker case
            for ticker in batch:
                if ticker in df.columns.get_level_values(0):
                    ticker_df = df[ticker].dropna(how="all")
                    if not ticker_df.empty:
                        self._save_ticker_data(ticker, ticker_df)

    def _save_ticker_data(self, ticker: str, df: pd.DataFrame):
        """Append to BronzeStockPrice table."""
        # Clean column names to lowercase
        df.columns = [str(c).lower() for c in df.columns]
        
        objects_to_create = []
        for index, row in df.iterrows():
            if pd.isna(row.get('close')):
                continue
                
            # Handle tz-aware vs naive
            if hasattr(index, "tz_convert"):
                candle_at = pd.Timestamp(index).tz_localize(None).to_pydatetime()
                date_val = candle_at.date()
            else:
                candle_at = pd.Timestamp(index).to_pydatetime()
                date_val = candle_at.date()
            if timezone.is_naive(candle_at):
                candle_at = timezone.make_aware(candle_at, timezone=dt_timezone.utc)
                
            # Create a single row object
            objects_to_create.append(
                BronzeStockPrice(
                    ticker=ticker.upper(),
                    company=ticker.upper(),
                    date=date_val,
                    candle_at=candle_at,
                    open=row.get('open'),
                    high=row.get('high'),
                    low=row.get('low'),
                    close=row.get('close'),
                    volume=row.get('volume', 0),
                    ingested_at=timezone.now(),
                    fetch_run_id=self.fetch_run_id,
                )
            )
            
        # Bulk create ignoring conflicts (DB append-only requirement)
        if objects_to_create:
            try:
                BronzeStockPrice.objects.bulk_create(
                    objects_to_create, 
                    ignore_conflicts=True
                )
            except Exception as e:
                logger.error(f"Bulk create failed for {ticker}: {e}")


RETRY_ATTEMPTS = 3
RETRY_DELAY = 2


def fetch_fundamentals_for_ticker(ticker: str) -> dict:
    """
    Fetch fundamental data for a single ticker using yfinance.
    Returns dict of fundamentals or empty dict on failure.
    Called ONLY during initial seeding - not on user requests.
    """
    import yfinance as yf

    def safe(val):
        if val is None:
            return None
        try:
            f = float(val)
            if f != f or f == float("inf") or f == float("-inf"):
                return None
            return f
        except (TypeError, ValueError):
            return None

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            t = yf.Ticker(ticker)
            info = t.info

            if not info or len(info) < 5:
                logger.warning(f"[{ticker}] Empty info (attempt {attempt})")
                if attempt < RETRY_ATTEMPTS:
                    time.sleep(RETRY_DELAY)
                continue

            return {
                "trailing_pe": safe(info.get("trailingPE")),
                "forward_pe": safe(info.get("forwardPE")),
                "price_to_book": safe(info.get("priceToBook")),
                "price_to_sales": safe(info.get("priceToSalesTrailing12Months")),
                "enterprise_value": safe(info.get("enterpriseValue")),
                "ev_to_ebitda": safe(info.get("enterpriseToEbitda")),
                "profit_margin": safe(info.get("profitMargins")),
                "operating_margin": safe(info.get("operatingMargins")),
                "gross_margin": safe(info.get("grossMargins")),
                "return_on_equity": safe(info.get("returnOnEquity")),
                "return_on_assets": safe(info.get("returnOnAssets")),
                "revenue_growth": safe(info.get("revenueGrowth")),
                "earnings_growth": safe(info.get("earningsGrowth")),
                "eps_trailing": safe(info.get("trailingEps")),
                "eps_forward": safe(info.get("forwardEps")),
                "market_cap": safe(info.get("marketCap")),
                "total_revenue": safe(info.get("totalRevenue")),
                "free_cashflow": safe(info.get("freeCashflow")),
                "debt_to_equity": safe(info.get("debtToEquity")),
                "current_ratio": safe(info.get("currentRatio")),
                "beta": safe(info.get("beta")),
                "week52_high": safe(info.get("fiftyTwoWeekHigh")),
                "week52_low": safe(info.get("fiftyTwoWeekLow")),
                "dividend_yield": safe(info.get("dividendYield")),
            }

        except Exception as e:
            logger.error(f"[{ticker}] Fundamentals attempt {attempt} failed: {e}")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY)

    logger.error(f"[{ticker}] All fundamentals attempts failed")
    return {}


def fetch_fundamentals_batch(tickers: list) -> dict:
    """
    Fetch fundamentals for all tickers in batches of 10
    with 3s sleep between batches (fundamentals are heavier than OHLCV).
    Returns dict: {ticker: fundamentals_dict}
    """
    fund_batch_size = 10
    fund_batch_sleep = 3
    results = {}
    total = len(tickers)

    for i in range(0, total, fund_batch_size):
        batch = tickers[i : i + fund_batch_size]
        batch_num = i // fund_batch_size + 1
        total_batches = (total + fund_batch_size - 1) // fund_batch_size
        logger.info(f"Fundamentals batch {batch_num}/{total_batches}: {batch}")

        for ticker in batch:
            results[ticker] = fetch_fundamentals_for_ticker(ticker)
            time.sleep(0.5)  # small delay between individual tickers

        if i + fund_batch_size < total:
            logger.info(f"Fundamentals batch done. Sleeping {fund_batch_sleep}s...")
            time.sleep(fund_batch_sleep)

    success = sum(1 for v in results.values() if v)
    logger.info(f"Fundamentals fetch complete: {success}/{total} succeeded")
    return results
