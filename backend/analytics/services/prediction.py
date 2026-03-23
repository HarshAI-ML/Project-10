"""
prediction.py — DB-only replacement.
Previously called yf.download() for both freshness check and history.
Now uses get_stock_history() from data_access. yfinance NOT imported.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from django.core.cache import cache
from django.utils import timezone
from sklearn.linear_model import LinearRegression

from analytics.data_access import get_stock_history

CACHE_TTL_SECONDS = 60 * 60 * 24
CHECK_TTL_SECONDS = 60 * 60 * 6
MIN_DATA_POINTS = 60
FUTURE_DAYS = 1


def _cache_key(symbol: str) -> str:
    return f"stock_prediction:{symbol.upper()}"


def _check_key(symbol: str) -> str:
    return f"stock_prediction_check:{symbol.upper()}"


def _load_history_frame(symbol: str) -> pd.DataFrame:
    """Load history from BronzeStockPrice and format for LinearRegression."""
    df = get_stock_history(symbol, days=365)
    if df.empty:
        return pd.DataFrame(columns=["Date", "Adj Close", "Day"])

    df = df.rename(columns={"date": "Date", "close": "Adj Close"})
    df = df.dropna(subset=["Adj Close"]).reset_index(drop=True)
    df["Day"] = range(len(df))
    return df


def _latest_data_date(symbol: str) -> str | None:
    """Get the most recent Bronze data date for freshness check."""
    df = get_stock_history(symbol, days=10)
    if df.empty:
        return None
    return df["date"].max().strftime("%Y-%m-%d")


def _result_payload(
    status: str,
    predicted_price_1d: float | None = None,
    expected_change_pct: float | None = None,
    direction_signal: str | None = None,
    model_confidence_r2: float | None = None,
    last_data_date: str | None = None,
) -> dict[str, Any]:
    return {
        "status":              status,
        "predicted_price_1d":  predicted_price_1d,
        "expected_change_pct": expected_change_pct,
        "direction_signal":    direction_signal,
        "model_confidence_r2": model_confidence_r2,
        "last_data_date":      last_data_date,
    }


def _recommended_action(expected_change_pct: float | None, status: str) -> str:
    if status != "ok":
        return "Unavailable" if status == "unavailable" else "Insufficient Data"
    if expected_change_pct is None:
        return "Hold"
    if expected_change_pct >= 2:
        return "Buy Bias"
    if expected_change_pct <= -2:
        return "Reduce Bias"
    return "Hold/Watch"


def _normalized_payload(payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("status", "unavailable")
    expected_change = payload.get("expected_change_pct")
    return {
        "predicted_price_1d":  payload.get("predicted_price_1d"),
        "expected_change_pct": expected_change,
        "direction_signal":    payload.get("direction_signal") or "",
        "model_confidence_r2": payload.get("model_confidence_r2"),
        "prediction_status":   status,
        "recommended_action":  _recommended_action(expected_change, status),
        "prediction_updated_at": timezone.now(),
    }


def _compute_prediction(symbol: str) -> dict[str, Any]:
    df = _load_history_frame(symbol)
    if len(df) < MIN_DATA_POINTS:
        last_date = df["Date"].iloc[-1].strftime("%Y-%m-%d") if len(df) else None
        return _result_payload(status="insufficient_data", last_data_date=last_date)

    try:
        x = df[["Day"]]
        y = df["Adj Close"]
        model = LinearRegression()
        model.fit(x, y)

        future_day = pd.DataFrame({"Day": [int(df["Day"].iloc[-1]) + FUTURE_DAYS]})
        predicted_price = float(model.predict(future_day)[0])
        today_price = float(df["Adj Close"].iloc[-1])
        expected_change_pct = ((predicted_price - today_price) / today_price) * 100 if today_price else 0.0
        direction_signal = "↑ Increase" if predicted_price > today_price else "↓ Decrease"
        confidence = float(model.score(x, y))

        return _result_payload(
            status="ok",
            predicted_price_1d=round(predicted_price, 2),
            expected_change_pct=round(expected_change_pct, 2),
            direction_signal=direction_signal,
            model_confidence_r2=round(confidence, 2),
            last_data_date=df["Date"].iloc[-1].strftime("%Y-%m-%d"),
        )
    except Exception:
        last_date = df["Date"].iloc[-1].strftime("%Y-%m-%d") if len(df) else None
        return _result_payload(status="unavailable", last_data_date=last_date)


def get_stock_prediction(symbol: str) -> dict[str, Any]:
    ticker_symbol = str(symbol or "").strip().upper()
    if not ticker_symbol:
        return _result_payload(status="unavailable")

    cache_key = _cache_key(ticker_symbol)
    freshness_key = _check_key(ticker_symbol)
    cached = cache.get(cache_key)
    if cached:
        if cache.get(freshness_key):
            return cached
        latest_date = _latest_data_date(ticker_symbol)
        cached_last_date = cached.get("last_data_date")
        if not latest_date or latest_date <= str(cached_last_date):
            cache.set(freshness_key, True, CHECK_TTL_SECONDS)
            return cached

    result = _compute_prediction(ticker_symbol)
    cache.set(cache_key, result, CACHE_TTL_SECONDS)
    cache.set(freshness_key, True, CHECK_TTL_SECONDS)
    return result


def refresh_stock_prediction(stock) -> dict[str, Any]:
    payload = get_stock_prediction(stock.symbol)
    update_data = _normalized_payload(payload)
    for field, value in update_data.items():
        setattr(stock, field, value)
    stock.save(update_fields=list(update_data.keys()))
    return update_data
