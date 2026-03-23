"""
Silver processor: Bronze → SilverCleanedPrice
Computes technical indicators for all 400 stocks using pandas.
"""
import pandas as pd
import numpy as np
import logging
from pipeline.models import BronzeStockPrice, SilverCleanedPrice
from portfolio.models import Stock

logger = logging.getLogger(__name__)


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI using Wilder's smoothing method."""
    delta = series.diff()
    gain  = delta.where(delta > 0, 0.0)
    loss  = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.round(4)


def compute_macd(series: pd.Series, fast=12, slow=26, signal=9):
    """Compute MACD line, signal line, and histogram."""
    ema_fast   = series.ewm(span=fast,   adjust=False).mean()
    ema_slow   = series.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line
    return macd_line.round(4), signal_line.round(4), histogram.round(4)


def compute_bollinger(series: pd.Series, period: int = 20):
    """Compute Bollinger Bands."""
    ma    = series.rolling(window=period).mean()
    std   = series.rolling(window=period).std()
    upper = (ma + 2 * std).round(4)
    lower = (ma - 2 * std).round(4)
    width = ((upper - lower) / ma.replace(0, np.nan)).round(4)
    return upper, lower, width


def process_ticker(ticker: str, stock_meta: dict) -> int:
    """
    Process a single ticker: read Bronze, compute indicators, write Silver.
    Returns number of rows written.
    """
    qs = (
        BronzeStockPrice.objects
        .filter(ticker=ticker)
        .order_by('date')
        .values('date', 'open', 'high', 'low', 'close', 'volume')
    )

    if not qs.exists():
        logger.warning(f"[{ticker}] No Bronze data, skipping")
        return 0

    df = pd.DataFrame(list(qs))
    df['date']  = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    # Drop rows with null or zero close
    df = df.dropna(subset=['close'])
    df = df[df['close'] > 0]

    if len(df) < 2:
        logger.warning(f"[{ticker}] Insufficient data ({len(df)} rows), skipping")
        return 0

    close = df['close']

    # Returns
    df['daily_return']  = close.pct_change().round(6)
    df['log_return']    = np.log(close / close.shift(1)).round(6)

    # Moving averages
    df['ma_5']   = close.rolling(5).mean().round(4)
    df['ma_20']  = close.rolling(20).mean().round(4)
    df['ma_50']  = close.rolling(50).mean().round(4)
    df['ma_200'] = close.rolling(200).mean().round(4)

    # Volatility
    df['volatility_20'] = df['daily_return'].rolling(20).std().round(6)

    # RSI
    df['rsi_14'] = compute_rsi(close, 14)

    # MACD
    df['macd'], df['macd_signal'], df['macd_hist'] = compute_macd(close)

    # Bollinger Bands
    df['bb_upper'], df['bb_lower'], df['bb_width'] = compute_bollinger(close)

    # Price vs MA signals
    df['price_vs_ma20'] = ((close - df['ma_20']) / df['ma_20'].replace(0, np.nan) * 100).round(4)
    df['price_vs_ma50'] = ((close - df['ma_50']) / df['ma_50'].replace(0, np.nan) * 100).round(4)

    # Replace NaN with None for DB
    df = df.where(pd.notnull(df), None)

    # Delete existing Silver rows for this ticker and reinsert
    SilverCleanedPrice.objects.filter(ticker=ticker).delete()

    rows = []
    for _, row in df.iterrows():
        rows.append(SilverCleanedPrice(
            ticker        = ticker,
            company       = stock_meta.get('company', ''),
            sector        = stock_meta.get('sector', ''),
            geography     = stock_meta.get('geography', ''),
            date          = row['date'].date(),
            open          = row.get('open'),
            high          = row.get('high'),
            low           = row.get('low'),
            close         = row.get('close'),
            volume        = int(row['volume']) if row.get('volume') else None,
            daily_return  = row.get('daily_return'),
            log_return    = row.get('log_return'),
            ma_5          = row.get('ma_5'),
            ma_20         = row.get('ma_20'),
            ma_50         = row.get('ma_50'),
            ma_200        = row.get('ma_200'),
            volatility_20 = row.get('volatility_20'),
            rsi_14        = row.get('rsi_14'),
            macd          = row.get('macd'),
            macd_signal   = row.get('macd_signal'),
            macd_hist     = row.get('macd_hist'),
            bb_upper      = row.get('bb_upper'),
            bb_lower      = row.get('bb_lower'),
            bb_width      = row.get('bb_width'),
            price_vs_ma20 = row.get('price_vs_ma20'),
            price_vs_ma50 = row.get('price_vs_ma50'),
        ))

    SilverCleanedPrice.objects.bulk_create(rows, batch_size=500)
    return len(rows)


def process_all_tickers() -> dict:
    """
    Process all active tickers from Bronze → Silver.
    Returns summary dict.
    """
    stocks = (
        Stock.objects
        .filter(is_active=True)
        .exclude(ticker__isnull=True)
        .exclude(ticker='')
        .values('ticker', 'name', 'company_name', 'sector', 'geography')
    )

    stock_meta = {
        s['ticker']: {
            'company':   s['name'] or s['company_name'] or '',
            'sector':    s['sector'] or '',
            'geography': s['geography'] or '',
        }
        for s in stocks
    }

    tickers = list(stock_meta.keys())
    logger.info(f"Processing {len(tickers)} tickers Bronze → Silver")

    success = 0
    failed  = 0
    total_rows = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            rows = process_ticker(ticker, stock_meta[ticker])
            total_rows += rows
            success += 1
            if i % 50 == 0 or i == len(tickers):
                logger.info(f"Progress: {i}/{len(tickers)} | rows so far: {total_rows}")
        except Exception as e:
            failed += 1
            logger.error(f"[{ticker}] Failed: {e}")

    return {
        'tickers_success': success,
        'tickers_failed':  failed,
        'total_rows':      total_rows,
    }
