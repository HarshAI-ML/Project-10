"""
fetch_data.py — DB-only replacement.
Previously called yfinance.Ticker().history().
Now reads from BronzeStockPrice via data_access.
yfinance is NOT imported here.
"""
from __future__ import annotations

import logging

from analytics.data_access import get_stock_history

logger = logging.getLogger(__name__)


def fetch_data(symbol: str, days: int = 365) -> list[dict]:
    """
    Return historical close prices from BronzeStockPrice.
    Returns list of {'date': str, 'close': float}.
    Returns [] if no Bronze data exists — never falls back to yfinance.
    """
    df = get_stock_history(symbol, days=days)
    if df.empty:
        logger.warning(f"[fetch_data] No Bronze data for {symbol}")
        return []

    rows = [
        {
            "date":  row["date"].strftime("%Y-%m-%d"),
            "close": round(float(row["close"]), 2),
        }
        for _, row in df.iterrows()
        if row.get("close") is not None
    ]
    return rows
