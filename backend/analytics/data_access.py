"""
Central data access layer — Bronze layer reads.
ALL stock data queries go through here.
No other file outside this module should import BronzeStockPrice directly.
yfinance is NEVER called here — data comes from BronzeStockPrice (populated by the pipeline).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd
from django.db.models import Max, Min

from pipeline.models import BronzeStockPrice
from portfolio.models import StockMaster

logger = logging.getLogger(__name__)

NO_DATA_RESPONSE = {"error": "Data not yet available. Pipeline runs hourly."}


# ---------------------------------------------------------------------------
# OHLCV history helpers
# ---------------------------------------------------------------------------

def get_stock_history(ticker: str, days: int = 365) -> pd.DataFrame:
    """
    Get historical OHLCV for a single ticker from BronzeStockPrice.
    Returns DataFrame with columns: date, open, high, low, close, volume.
    Returns empty DataFrame if no Bronze data found — never calls yfinance.
    """
    cutoff = date.today() - timedelta(days=days)
    qs = (
        BronzeStockPrice.objects
        .filter(ticker=ticker, date__gte=cutoff)
        .order_by('date')
        .values('date', 'open', 'high', 'low', 'close', 'volume')
    )
    if not qs.exists():
        logger.warning(f"[data_access] No Bronze data for {ticker}")
        return pd.DataFrame()

    df = pd.DataFrame(list(qs))
    df['date'] = pd.to_datetime(df['date'])
    return df


def get_multiple_stocks_history(tickers: list, days: int = 365) -> dict:
    """
    Get historical OHLCV for multiple tickers in one DB query.
    Returns dict: {ticker: DataFrame}
    """
    cutoff = date.today() - timedelta(days=days)
    qs = (
        BronzeStockPrice.objects
        .filter(ticker__in=tickers, date__gte=cutoff)
        .order_by('ticker', 'date')
        .values('ticker', 'date', 'open', 'high', 'low', 'close', 'volume')
    )

    bucket: dict[str, list] = {t: [] for t in tickers}
    for row in qs:
        bucket[row['ticker']].append(row)

    dfs: dict[str, pd.DataFrame] = {}
    for ticker, rows in bucket.items():
        if rows:
            df = pd.DataFrame(rows)
            df['date'] = pd.to_datetime(df['date'])
            dfs[ticker] = df
        else:
            logger.warning(f"[data_access] No Bronze data for {ticker}")
            dfs[ticker] = pd.DataFrame()
    return dfs


def get_latest_price(ticker: str) -> dict | None:
    """
    Get the most recent price row for a ticker from BronzeStockPrice.
    Returns dict with date, open, high, low, close, volume or None.
    """
    return (
        BronzeStockPrice.objects
        .filter(ticker=ticker)
        .order_by('-date')
        .values('date', 'open', 'high', 'low', 'close', 'volume')
        .first()
    )


def get_latest_prices_bulk(tickers: list) -> dict:
    """
    Get latest price for multiple tickers.
    Returns dict: {ticker: {date, open, high, low, close, volume}}
    """
    max_dates = (
        BronzeStockPrice.objects
        .filter(ticker__in=tickers)
        .values('ticker')
        .annotate(max_date=Max('date'))
    )
    results: dict[str, Any] = {}
    for entry in max_dates:
        ticker   = entry['ticker']
        max_date = entry['max_date']
        row = (
            BronzeStockPrice.objects
            .filter(ticker=ticker, date=max_date)
            .values('date', 'open', 'high', 'low', 'close', 'volume')
            .first()
        )
        if row:
            results[ticker] = row
    return results


def get_52_week_range(ticker: str) -> dict:
    """Get 52-week high and low from BronzeStockPrice."""
    cutoff = date.today() - timedelta(days=365)
    return (
        BronzeStockPrice.objects
        .filter(ticker=ticker, date__gte=cutoff)
        .aggregate(week52_high=Max('high'), week52_low=Min('low'))
    )


def has_data(ticker: str) -> bool:
    """Check if any Bronze data exists for this ticker."""
    return BronzeStockPrice.objects.filter(ticker=ticker).exists()


# ---------------------------------------------------------------------------
# Stock master table helpers (no yfinance — reads portfolio_stock table)
# ---------------------------------------------------------------------------

def search_stocks(query: str, geography: str | None = None) -> list:
    """
    Search the Stock catalogue by ticker / name / sector.
    Returns list of dicts. Never calls yfinance.
    """
    qs = StockMaster.objects.filter(is_active=True)
    if geography:
        qs = qs.filter(geography=geography)
    if query:
        from django.db.models import Q
        qs = qs.filter(
            Q(ticker__icontains=query)
            | Q(name__icontains=query)
            | Q(sector__icontains=query)
        )
    return list(qs.values('ticker', 'name', 'sector', 'geography')[:50])


def get_stock_info(ticker: str) -> dict | None:
    """
    Get static metadata for a ticker from the Stock catalogue.
    Returns dict or None if not found.
    """
    try:
        s = StockMaster.objects.get(ticker=ticker, is_active=True)
        return {
            'ticker':    s.ticker,
            'name':      s.name,
            'sector':    s.sector,
            'geography': s.geography,
            'is_active': s.is_active,
        }
    except StockMaster.DoesNotExist:
        return None


def get_sector_stocks(sector: str) -> list:
    """Get all active stocks in a given sector."""
    return list(
        StockMaster.objects
        .filter(sector=sector, is_active=True)
        .values('ticker', 'name', 'sector', 'geography')
    )


def get_all_active_tickers() -> list:
    """Return all active ticker symbols."""
    return list(
        StockMaster.objects
        .filter(is_active=True)
        .values_list('ticker', flat=True)
    )

def get_silver_history(ticker: str, days: int = 365) -> pd.DataFrame:
    """
    Get cleaned + enriched price history from Silver layer.
    Preferred over get_stock_history for analytics — has indicators pre-computed.
    Returns DataFrame with all Silver columns.
    """
    from pipeline.models import SilverCleanedPrice
    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=days)

    qs = (
        SilverCleanedPrice.objects
        .filter(ticker=ticker, date__gte=cutoff)
        .order_by('date')
        .values(
            'date', 'open', 'high', 'low', 'close', 'volume',
            'daily_return', 'log_return',
            'ma_5', 'ma_20', 'ma_50', 'ma_200',
            'volatility_20', 'rsi_14',
            'macd', 'macd_signal', 'macd_hist',
            'bb_upper', 'bb_lower', 'bb_width',
            'price_vs_ma20', 'price_vs_ma50',
        )
    )

    if not qs.exists():
        logger.warning(f"No Silver data for {ticker}, falling back to Bronze")
        return get_stock_history(ticker, days=days)

    df = pd.DataFrame(list(qs))
    df['date'] = pd.to_datetime(df['date'])
    return df


def get_latest_silver(ticker: str) -> dict:
    """
    Get the most recent Silver row for a ticker.
    Used for stock detail pages — has RSI, MACD, MA signals pre-computed.
    """
    from pipeline.models import SilverCleanedPrice
    row = (
        SilverCleanedPrice.objects
        .filter(ticker=ticker)
        .order_by('-date')
        .values(
            'date', 'close', 'daily_return',
            'ma_20', 'ma_50', 'ma_200',
            'rsi_14', 'macd', 'macd_signal',
            'bb_upper', 'bb_lower',
            'price_vs_ma20', 'price_vs_ma50',
            'volatility_20',
        )
        .first()
    )
    return row


def get_sector_silver_summary(sector: str) -> list:
    """
    Get latest Silver data for all stocks in a sector.
    Used for sector heatmap on home page.
    """
    from pipeline.models import SilverCleanedPrice
    from django.db.models import Max

    tickers = get_sector_stocks(sector)
    ticker_list = [t['ticker'] for t in tickers]

    max_dates = (
        SilverCleanedPrice.objects
        .filter(ticker__in=ticker_list)
        .values('ticker')
        .annotate(max_date=Max('date'))
    )

    results = []
    for entry in max_dates:
        row = (
            SilverCleanedPrice.objects
            .filter(ticker=entry['ticker'], date=entry['max_date'])
            .values('ticker', 'company', 'sector', 'close', 'daily_return',
                    'rsi_14', 'ma_20', 'price_vs_ma20', 'volatility_20')
            .first()
        )
        if row:
            results.append(row)

    return results


def get_fundamentals(ticker: str) -> dict:
    """
    Get latest fundamentals for a ticker from BronzeStockFundamentals.
    Returns dict or empty dict if not found.
    """
    from pipeline.models import BronzeStockFundamentals

    row = (
        BronzeStockFundamentals.objects
        .filter(ticker=ticker)
        .order_by("-fetched_at")
        .values(
            "trailing_pe", "forward_pe", "price_to_book",
            "profit_margin", "operating_margin", "gross_margin",
            "return_on_equity", "return_on_assets",
            "revenue_growth", "earnings_growth",
            "eps_trailing", "eps_forward",
            "market_cap", "debt_to_equity",
            "current_ratio", "beta",
            "week52_high", "week52_low",
            "dividend_yield", "fetched_at",
        )
        .first()
    )
    return dict(row) if row else {}


def get_fundamentals_bulk(tickers: list) -> dict:
    """
    Get latest fundamentals for multiple tickers in one query.
    Returns dict: {ticker: fundamentals_dict}
    """
    from pipeline.models import BronzeStockFundamentals
    from django.db.models import Max

    latest = (
        BronzeStockFundamentals.objects
        .filter(ticker__in=tickers)
        .values("ticker")
        .annotate(latest=Max("fetched_at"))
    )

    results = {}
    for entry in latest:
        row = (
            BronzeStockFundamentals.objects
            .filter(ticker=entry["ticker"], fetched_at=entry["latest"])
            .values(
                "trailing_pe", "forward_pe", "price_to_book",
                "profit_margin", "operating_margin", "gross_margin",
                "return_on_equity", "return_on_assets",
                "revenue_growth", "earnings_growth",
                "eps_trailing", "eps_forward",
                "market_cap", "debt_to_equity",
                "current_ratio", "beta",
                "week52_high", "week52_low",
                "dividend_yield",
            )
            .first()
        )
        if row:
            results[entry["ticker"]] = dict(row)

    return results


def get_latest_signal(ticker: str) -> dict:
    """Get latest GoldStockSignal for a ticker."""
    from pipeline.models import GoldStockSignal

    row = (
        GoldStockSignal.objects
        .filter(ticker=ticker)
        .order_by("-date")
        .values(
            "signal",
            "confidence",
            "rsi_signal",
            "macd_signal",
            "ma_signal",
            "rsi_14",
            "close",
            "price_vs_ma20",
            "date",
        )
        .first()
    )
    return dict(row) if row else {}


def get_latest_signals_bulk(tickers: list) -> dict:
    """Get latest signal for multiple tickers in one query."""
    from django.db.models import Max
    from pipeline.models import GoldStockSignal

    latest_dates = (
        GoldStockSignal.objects
        .filter(ticker__in=tickers)
        .values("ticker")
        .annotate(max_date=Max("date"))
    )

    results = {}
    for entry in latest_dates:
        row = (
            GoldStockSignal.objects
            .filter(ticker=entry["ticker"], date=entry["max_date"])
            .values("signal", "confidence", "rsi_signal", "macd_signal", "ma_signal", "rsi_14", "close")
            .first()
        )
        if row:
            results[entry["ticker"]] = dict(row)

    return results


def get_latest_forecast(ticker: str) -> dict:
    """Get latest GoldForecastResult for a ticker."""
    from pipeline.models import GoldForecastResult

    row = (
        GoldForecastResult.objects
        .filter(ticker=ticker)
        .order_by("-forecast_date")
        .values(
            "predicted_price",
            "current_price",
            "expected_change_pct",
            "direction",
            "confidence_r2",
            "model_type",
            "forecast_date",
        )
        .first()
    )
    return dict(row) if row else {}


def get_latest_forecasts_bulk(tickers: list) -> dict:
    """Get latest forecast for multiple tickers in one query."""
    from django.db.models import Max
    from pipeline.models import GoldForecastResult

    latest_dates = (
        GoldForecastResult.objects
        .filter(ticker__in=tickers)
        .values("ticker")
        .annotate(max_date=Max("forecast_date"))
    )

    results = {}
    for entry in latest_dates:
        row = (
            GoldForecastResult.objects
            .filter(ticker=entry["ticker"], forecast_date=entry["max_date"])
            .values(
                "predicted_price",
                "current_price",
                "expected_change_pct",
                "direction",
                "confidence_r2",
                "model_type",
            )
            .first()
        )
        if row:
            results[entry["ticker"]] = dict(row)

    return results


def get_latest_insight(ticker: str) -> dict:
    """Get latest GoldStockInsight for a ticker."""
    from pipeline.models import GoldStockInsight

    row = (
        GoldStockInsight.objects
        .filter(ticker=ticker)
        .order_by("-date")
        .values(
            "ticker",
            "date",
            "pe_ratio",
            "discount_level",
            "opportunity_score",
            "graph_data",
            "updated_at",
        )
        .first()
    )
    return dict(row) if row else {}


def get_latest_insights_bulk(tickers: list) -> dict:
    """Get latest GoldStockInsight for multiple tickers in one query."""
    from django.db.models import Max
    from pipeline.models import GoldStockInsight

    latest_dates = (
        GoldStockInsight.objects
        .filter(ticker__in=tickers)
        .values("ticker")
        .annotate(max_date=Max("date"))
    )

    results = {}
    for entry in latest_dates:
        row = (
            GoldStockInsight.objects
            .filter(ticker=entry["ticker"], date=entry["max_date"])
            .values(
                "date",
                "pe_ratio",
                "discount_level",
                "opportunity_score",
                "graph_data",
                "updated_at",
            )
            .first()
        )
        if row:
            results[entry["ticker"]] = dict(row)

    return results
