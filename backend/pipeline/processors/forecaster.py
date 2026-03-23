"""
Silver -> Gold: run Linear Regression predictions for all 400 stocks.
Reads from SilverCleanedPrice, writes to GoldForecastResult.
Optimized for faster training than tree ensembles.
"""
import logging
from datetime import timedelta

import numpy as np
import pandas as pd

from pipeline.models import GoldForecastResult, SilverCleanedPrice
from portfolio.models import StockMaster

logger = logging.getLogger(__name__)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build feature matrix from Silver data for Linear Regression."""
    df = df.copy().sort_values("date").reset_index(drop=True)

    for lag in [1, 2, 3, 5, 10]:
        df[f"close_lag_{lag}"] = df["close"].shift(lag)
        df[f"return_lag_{lag}"] = df["daily_return"].shift(lag)

    df["rolling_mean_5"] = df["close"].rolling(5).mean()
    df["rolling_std_5"] = df["close"].rolling(5).std()
    df["rolling_mean_10"] = df["close"].rolling(10).mean()

    feature_cols = [
        "close",
        "daily_return",
        "volatility_20",
        "rsi_14",
        "macd",
        "macd_signal",
        "macd_hist",
        "ma_5",
        "ma_20",
        "ma_50",
        "bb_width",
        "price_vs_ma20",
        "price_vs_ma50",
        "close_lag_1",
        "close_lag_2",
        "close_lag_3",
        "close_lag_5",
        "close_lag_10",
        "return_lag_1",
        "return_lag_2",
        "return_lag_3",
        "rolling_mean_5",
        "rolling_std_5",
        "rolling_mean_10",
    ]

    return df[feature_cols].dropna()


def predict_ticker(ticker: str, horizon_days: int = 1) -> dict:
    """
    Run Linear Regression prediction for a single ticker.
    Returns prediction dict or empty dict on failure.
    """
    try:
        from sklearn.linear_model import LinearRegression
        from sklearn.metrics import r2_score
    except ImportError:
        logger.error("scikit-learn not installed")
        return {}

    qs = (
        SilverCleanedPrice.objects.filter(ticker=ticker)
        .order_by("date")
        .values(
            "date",
            "close",
            "daily_return",
            "log_return",
            "volatility_20",
            "rsi_14",
            "macd",
            "macd_signal",
            "macd_hist",
            "ma_5",
            "ma_20",
            "ma_50",
            "bb_upper",
            "bb_lower",
            "bb_width",
            "price_vs_ma20",
            "price_vs_ma50",
        )
    )

    if qs.count() < 60:
        logger.warning(f"[{ticker}] Insufficient data for prediction ({qs.count()} rows)")
        return {}

    df = pd.DataFrame(list(qs))
    df["date"] = pd.to_datetime(df["date"])
    df["target"] = df["close"].shift(-horizon_days)
    df = df.dropna().sort_values("date").reset_index(drop=True)

    features_df = build_features(df)
    target = df["target"].reindex(features_df.index).dropna()
    features_df = features_df.loc[target.index]
    current_price = float(df["close"].iloc[-1])
    forecast_date = df["date"].iloc[-1].date() + timedelta(days=horizon_days)

    if len(features_df) < 30:
        return {}

    X = features_df.values
    y = target.values

    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    model = LinearRegression()
    model.fit(X_train, y_train)

    y_pred_test = model.predict(X_test)
    r2 = float(r2_score(y_test, y_pred_test))
    if r2 < 0:
        r2 = 0.0

    last_features = features_df.iloc[[-1]].values
    predicted_price = float(model.predict(last_features)[0])

    if abs(predicted_price - current_price) / current_price > 0.5:
        predicted_price = current_price * (
            1 + np.clip((predicted_price - current_price) / current_price, -0.05, 0.05)
        )

    expected_change_pct = round((predicted_price - current_price) / current_price * 100, 4)
    direction = "Increase" if predicted_price >= current_price else "Decrease"

    return {
        "ticker": ticker,
        "forecast_date": forecast_date,
        "predicted_price": round(predicted_price, 4),
        "current_price": round(current_price, 4),
        "expected_change_pct": expected_change_pct,
        "direction": direction,
        "confidence_r2": round(r2, 4),
        "model_type": "linear_regression",
        "horizon_days": horizon_days,
    }


def predict_all_tickers(horizon_days: int = 1) -> dict:
    """
    Run Linear Regression predictions for all active tickers.
    Writes results to GoldForecastResult.
    Returns summary dict.
    """
    tickers = list(
        StockMaster.objects.filter(is_active=True)
        .exclude(ticker__isnull=True)
        .exclude(ticker="")
        .values_list("ticker", flat=True)
    )

    logger.info(f"Running Linear Regression predictions for {len(tickers)} tickers")
    success = 0
    failed = 0
    skipped = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            result = predict_ticker(ticker, horizon_days)
            if not result:
                skipped += 1
                continue

            GoldForecastResult.objects.update_or_create(
                ticker=ticker,
                forecast_date=result["forecast_date"],
                model_type=result["model_type"],
                defaults={
                    "predicted_price": result["predicted_price"],
                    "current_price": result["current_price"],
                    "expected_change_pct": result["expected_change_pct"],
                    "direction": result["direction"],
                    "confidence_r2": result["confidence_r2"],
                    "horizon_days": result["horizon_days"],
                },
            )
            success += 1

            if i % 50 == 0 or i == len(tickers):
                logger.info(
                    f"Progress: {i}/{len(tickers)} | success={success} failed={failed} skipped={skipped}"
                )

        except Exception as e:
            failed += 1
            logger.error(f"[{ticker}] Prediction failed: {e}")

    logger.info(f"Predictions done: {success} success, {failed} failed, {skipped} skipped")
    return {"success": success, "failed": failed, "skipped": skipped, "total": len(tickers)}
