"""
yahoo_search.py — DB-only replacement.
Previously called yfinance for live-search, live-detail, and live-compare.
Now reads exclusively from BronzeStockPrice and the Stock catalogue via data_access.
yfinance is NOT imported here.

Exported API (unchanged — same function signatures consumed by api/views.py):
  - search_live_stocks(query, limit) -> list[dict]
  - fetch_live_stock_detail(symbol, period, interval) -> dict | None
  - fetch_live_stock_comparison(symbol_a, symbol_b, period, interval) -> dict
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.data_access import (
    get_fundamentals,
    get_52_week_range,
    get_latest_price,
    get_stock_history,
    get_stock_info,
    has_data,
    search_stocks,
)
from analytics.services.opportunity_engine import opportunity_engine
from scripts.nifty500_top200 import ALL_STOCKS

logger = logging.getLogger(__name__)

# Full universe lookup: ticker -> company name (400 stocks)
TICKERS = {ticker: name for ticker, name, sector, geography in ALL_STOCKS}

ALLOWED_PERIODS   = {"1mo", "3mo", "6mo", "1y", "2y", "3y", "5y", "10y", "max"}
ALLOWED_INTERVALS = {"1d", "1wk", "1mo"}
DATAFRAME_DIR     = Path(__file__).resolve().parents[1] / "dataframes"

# Maps period string to approximate days
_PERIOD_DAYS = {
    "1mo": 30, "3mo": 90, "6mo": 180,
    "1y": 365, "2y": 730, "3y": 1095,
    "5y": 1825, "10y": 3650, "max": 3650,
}

_NO_DATA = {"error": "Data not yet available. Pipeline runs hourly."}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _discount_level(min_price: float, max_price: float, current_price: float) -> str:
    if max_price <= min_price:
        return "MEDIUM"
    position = (current_price - min_price) / (max_price - min_price)
    if position <= 0.33:
        return "HIGH"
    if position <= 0.66:
        return "MEDIUM"
    return "LOW"


def _normalize_period(period: str | None) -> str:
    value = (period or "1y").strip().lower()
    return value if value in ALLOWED_PERIODS else "1y"


def _normalize_interval(interval: str | None) -> str:
    value = (interval or "1d").strip().lower()
    return value if value in ALLOWED_INTERVALS else "1d"


def _infer_currency(symbol: str) -> str:
    s = str(symbol or "").upper()
    return "INR" if (s.endswith(".NS") or s.endswith(".BO")) else "USD"


def _sanitize_symbol(symbol: str) -> str:
    text = str(symbol or "").upper()
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_") or "UNKNOWN"


def _compute_regression(df: pd.DataFrame, x_col: str = "x", y_col: str = "y") -> dict[str, float]:
    frame = df[[x_col, y_col]].dropna()
    n = len(frame)
    if n < 2:
        return {"slope": 0.0, "intercept": 0.0, "correlation": 0.0}

    sum_x  = float(frame[x_col].sum())
    sum_y  = float(frame[y_col].sum())
    sum_xy = float((frame[x_col] * frame[y_col]).sum())
    sum_x2 = float((frame[x_col] ** 2).sum())
    sum_y2 = float((frame[y_col] ** 2).sum())

    denom = (n * sum_x2) - (sum_x ** 2)
    slope     = 0.0 if denom == 0 else ((n * sum_xy) - (sum_x * sum_y)) / denom
    intercept = (sum_y - (slope * sum_x)) / n

    corr_num   = (n * sum_xy) - (sum_x * sum_y)
    corr_denom = (((n * sum_x2) - (sum_x ** 2)) * ((n * sum_y2) - (sum_y ** 2))) ** 0.5
    correlation = 0.0 if corr_denom == 0 else corr_num / corr_denom

    return {"slope": slope, "intercept": intercept, "correlation": correlation}


def _aligned_price_frame(stock_a: dict, stock_b: dict) -> pd.DataFrame:
    fa = pd.DataFrame({"date": stock_a["dates"], "price_a": stock_a["prices"]})
    fb = pd.DataFrame({"date": stock_b["dates"], "price_b": stock_b["prices"]})
    merged = fa.merge(fb, on="date", how="inner").dropna(subset=["price_a", "price_b"])
    return merged.sort_values("date").reset_index(drop=True)


def _save_comparison_dataframes(stock_a, stock_b, aligned_df, period, interval) -> None:
    try:
        DATAFRAME_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        prefix = f"{_sanitize_symbol(stock_a['symbol'])}_{_sanitize_symbol(stock_b['symbol'])}_{period}_{interval}_{ts}"
        pd.DataFrame({"date": stock_a["dates"], "price": stock_a["prices"]}).to_csv(
            DATAFRAME_DIR / f"{prefix}_stock_a.csv", index=False
        )
        pd.DataFrame({"date": stock_b["dates"], "price": stock_b["prices"]}).to_csv(
            DATAFRAME_DIR / f"{prefix}_stock_b.csv", index=False
        )
        aligned_df.to_csv(DATAFRAME_DIR / f"{prefix}_aligned.csv", index=False)
    except Exception as exc:
        logger.warning(f"Could not save comparison dataframes: {exc}")


def _build_ticker_payload(symbol: str, period: str) -> dict[str, Any] | None:
    """
    Build the stock detail payload from BronzeStockPrice.
    Returns None if no data exists (never calls yfinance).
    """
    days = _PERIOD_DAYS.get(period, 365)
    df = get_stock_history(symbol, days=days)
    if df.empty:
        logger.warning(f"[yahoo_search] No Bronze data for {symbol}")
        return None

    info = get_stock_info(symbol) or {}
    fundamentals = get_fundamentals(symbol)
    company_name = info.get("name") or symbol
    currency     = _infer_currency(symbol)

    # Sort by date ascending
    df = df.sort_values("date")
    dates  = [d.strftime("%Y-%m-%d") for d in df["date"]]
    prices = [round(float(v), 4) for v in df["close"]]

    current_price = prices[-1]
    min_price     = min(prices)
    max_price     = max(prices)
    moving_avg    = [
        round(float(df["close"].iloc[max(0, i - 4): i + 1].mean()), 4)
        for i in range(len(df))
    ]

    return {
        "symbol":        symbol,
        "company_name":  company_name,
        "currency":      currency,
        "pe_ratio":      fundamentals.get("trailing_pe"),
        "forward_pe":    fundamentals.get("forward_pe"),
        "profit_margin": fundamentals.get("profit_margin"),
        "revenue_growth": fundamentals.get("revenue_growth"),
        "market_cap":    fundamentals.get("market_cap"),
        "beta":          fundamentals.get("beta"),
        "current_price": round(current_price, 2),
        "min_price":     round(min_price, 2),
        "max_price":     round(max_price, 2),
        "today_price":   round(current_price, 2),
        "dates":         dates,
        "prices":        prices,
        "moving_avg":    moving_avg,
        "price_map":     {dates[i]: prices[i] for i in range(len(dates))},
    }


# ---------------------------------------------------------------------------
# Public API — same signatures as before
# ---------------------------------------------------------------------------

def search_live_stocks(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Search stocks from the local DB catalogue (portfolio_stock table).
    Never calls yfinance.
    """
    if not query.strip():
        return []

    rows = search_stocks(query)[:limit]
    results: list[dict[str, Any]] = []

    for row in rows:
        ticker = row.get("ticker") or row.get("symbol", "")
        name   = row.get("name") or row.get("company_name") or ticker

        latest = get_latest_price(ticker) if ticker else None
        close  = round(float(latest["close"]), 2) if latest and latest.get("close") else None

        results.append({
            "id":            None,
            "symbol":        ticker,
            "company_name":  name,
            "sector":        row.get("sector", ""),
            "geography":     row.get("geography", ""),
            "current_price": close,
            "min_price":     None,
            "max_price":     None,
            "closing_price": close,
            "pe_ratio":      None,
            "currency":      _infer_currency(ticker),
            "discount_level": "UNKNOWN",
            "is_live":       False,   # data is from DB, not live yfinance
        })

    return results


def fetch_live_stock_detail(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> dict[str, Any] | None:
    """
    Return stock detail from BronzeStockPrice.
    Returns None if no Bronze data exists — never calls yfinance.
    """
    ticker_symbol = symbol.strip().upper()
    if not ticker_symbol:
        return None

    normalized_period = _normalize_period(period)

    payload = _build_ticker_payload(ticker_symbol, normalized_period)
    if payload is None:
        return None

    prices        = payload["prices"]
    current_price = payload["current_price"]
    min_price     = payload["min_price"]
    max_price     = payload["max_price"]
    discount_level = _discount_level(min_price, max_price, current_price)
    pe_for_score = float(payload["pe_ratio"]) if payload.get("pe_ratio") is not None else 0.0
    opportunity_score = opportunity_engine(pe_ratio=pe_for_score, discount_level=discount_level)

    return {
        "id":            None,
        "portfolio":     None,
        "portfolio_name": "Global Search",
        "symbol":        ticker_symbol,
        "company_name":  payload["company_name"],
        "sector":        (get_stock_info(ticker_symbol) or {}).get("sector", ""),
        "currency":      payload["currency"],
        "current_price": current_price,
        "min_price":     min_price,
        "max_price":     max_price,
        "today_price":   current_price,
        "is_live":       False,
        "analytics": {
            "pe_ratio":         payload["pe_ratio"],
            "forward_pe":       payload["forward_pe"],
            "profit_margin":    payload["profit_margin"],
            "revenue_growth":   payload["revenue_growth"],
            "market_cap":       payload["market_cap"],
            "beta":             payload["beta"],
            "discount_level":   discount_level,
            "opportunity_score": opportunity_score,
            "graph_data": {
                "dates":      payload["dates"],
                "price":      prices,
                "moving_avg": payload["moving_avg"],
                "period":     normalized_period,
                "interval":   _normalize_interval(interval),
            },
            "last_updated": datetime.now(timezone.utc).isoformat(),
        },
    }


def fetch_live_stock_comparison(
    symbol_a: str,
    symbol_b: str,
    period: str = "5y",
    interval: str = "1d",
) -> dict[str, Any]:
    """
    Compare two stocks using Bronze OHLCV data.
    Never calls yfinance.
    """
    ticker_a = symbol_a.strip().upper()
    ticker_b = symbol_b.strip().upper()
    if not ticker_a or not ticker_b:
        raise ValueError("Both stock symbols are required.")
    if ticker_a == ticker_b:
        raise ValueError("Please select two different stocks.")

    normalized_period   = _normalize_period(period or "5y")
    normalized_interval = _normalize_interval(interval)

    stock_a = _build_ticker_payload(ticker_a, normalized_period)
    stock_b = _build_ticker_payload(ticker_b, normalized_period)

    if stock_a is None:
        raise ValueError(f"No data found for ticker: {ticker_a}. Pipeline runs hourly.")
    if stock_b is None:
        raise ValueError(f"No data found for ticker: {ticker_b}. Pipeline runs hourly.")

    aligned_df = _aligned_price_frame(stock_a, stock_b)
    _save_comparison_dataframes(stock_a, stock_b, aligned_df, normalized_period, normalized_interval)

    historical = [
        {
            "date":    str(row.date),
            "price_a": round(float(row.price_a), 4),
            "price_b": round(float(row.price_b), 4),
        }
        for row in aligned_df.itertuples(index=False)
    ]

    if len(historical) < 2:
        raise ValueError("Not enough overlapping data to compare selected stocks.")

    points_df = aligned_df.rename(columns={"price_a": "x", "price_b": "y"})
    regression = _compute_regression(points_df)
    points_df["y_fit"] = (regression["slope"] * points_df["x"]) + regression["intercept"]
    scatter = [
        {
            "date":  str(row.date),
            "x":     float(row.x),
            "y":     float(row.y),
            "y_fit": round(float(row.y_fit), 6),
        }
        for row in points_df.sort_values("x").itertuples(index=False)
    ]

    slope     = regression["slope"]
    intercept = regression["intercept"]

    return {
        "period":   normalized_period,
        "interval": normalized_interval,
        "stock_a": {
            "symbol":        stock_a["symbol"],
            "company_name":  stock_a["company_name"],
            "currency":      stock_a["currency"],
            "current_price": stock_a["current_price"],
            "min_price":     stock_a["min_price"],
            "max_price":     stock_a["max_price"],
            "today_price":   stock_a["today_price"],
            "pe_ratio":      stock_a["pe_ratio"],
        },
        "stock_b": {
            "symbol":        stock_b["symbol"],
            "company_name":  stock_b["company_name"],
            "currency":      stock_b["currency"],
            "current_price": stock_b["current_price"],
            "min_price":     stock_b["min_price"],
            "max_price":     stock_b["max_price"],
            "today_price":   stock_b["today_price"],
            "pe_ratio":      stock_b["pe_ratio"],
        },
        "historical": historical,
        "scatter":    scatter,
        "pearson_correlation": round(regression["correlation"], 6),
        "regression": {
            "slope":     round(slope, 6),
            "intercept": round(intercept, 6),
            "equation":  f"{ticker_b} = {slope:.6f} * {ticker_a} + {intercept:.6f}",
        },
    }
