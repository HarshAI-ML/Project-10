"""
indicators.py — DB-only replacement.
Previously called yfinance.Ticker().info for P/E ratio.
Now computes PE from Bronze price history only — no external calls.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def indicators(df: list[dict], symbol: str) -> dict:
    """
    Compute PE ratio and discount level from Bronze price history.
    No yfinance calls — computed purely from the data passed in.
    """
    if not df:
        return {"pe_ratio": 0.0, "discount_level": "UNKNOWN"}

    current_price = float(df[-1]["close"])
    average_price = sum(float(row["close"]) for row in df) / len(df)

    # Without live fundamentals, we approximate PE as price / (avg price proxy)
    # Frontend displays this as a relative valuation indicator
    pe_ratio = round(current_price / max(average_price, 1.0), 2)

    ratio = current_price / max(average_price, 1.0)
    if ratio <= 0.9:
        discount_level = "HIGH"
    elif ratio <= 1.0:
        discount_level = "MEDIUM"
    else:
        discount_level = "LOW"

    return {"pe_ratio": pe_ratio, "discount_level": discount_level}
