from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone as dt_timezone
from pathlib import Path
import json
from typing import Any

import numpy as np
import pandas as pd

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Min
from django.utils import timezone
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import MinMaxScaler, StandardScaler

from analytics.models import PredictionModelState, PredictionResultCache
from portfolio.models import StockMaster
from scripts.nifty500_top200 import ALL_STOCKS

# Full universe of supported tickers (400 stocks: Nifty 200 + S&P 500 top 200)
TICKERS = [ticker for ticker, name, sector, geography in ALL_STOCKS]


HISTORICAL_PERIODS = {
    "6mo": "6mo",
    "1y": "1y",
    "2y": "2y",
    "5y": "5y",
}
HOURLY_PERIOD_MAP = {
    "6mo": "180d",
    "1y": "365d",
    "2y": "730d",
    "5y": "730d",
}
MODEL_TYPES = {"xgboost", "lstm"}
PREDICTION_FREQUENCIES = {"daily", "weekly", "monthly"}
FORECAST_POINTS = {"daily": 30, "weekly": 12, "monthly": 6}
CACHE_VALID_HOURS = 24
HOURLY_CACHE_VALID_HOURS = 1
MODEL_REFRESH_WINDOWS = {"xgboost": timedelta(hours=24), "lstm": timedelta(days=3)}

HISTORICAL_PERIOD_OPTIONS = [
    {"value": "6mo", "label": "6 Months", "days": 180},
    {"value": "1y", "label": "1 Year", "days": 365},
    {"value": "2y", "label": "2 Years", "days": 730},
    {"value": "5y", "label": "5 Years", "days": 1825},
]

FEATURE_COLUMNS = [
    "close",
    "returns_1d",
    "sma_5",
    "sma_10",
    "sma_20",
    "ema_12",
    "ema_26",
    "rsi_14",
    "volatility_10",
]


def _get_plt():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except Exception as exc:
        raise RuntimeError(
            "matplotlib is not installed. Install dependencies from requirements-prediction.txt."
        ) from exc


def _prediction_root() -> Path:
    root = Path(getattr(settings, "PREDICTIONS_ROOT", settings.BASE_DIR / "predictions"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.lower())


def _plot_rel_path(symbol: str, model: str, filename: str) -> str:
    return f"{_safe_slug(symbol)}/{_safe_slug(model)}/{filename}"


def _plot_abs_path(symbol: str, model: str, filename: str) -> Path:
    path = _prediction_root() / _plot_rel_path(symbol, model, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _save_forecast_json(symbol: str, model: str, payload: dict[str, Any]) -> str:
    filename = "forecast_data.json"
    abs_path = _plot_abs_path(symbol, model, filename)
    with abs_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
    return _plot_rel_path(symbol, model, filename)


def _build_plot_url(path: str, request=None) -> str:
    base = getattr(settings, "PREDICTIONS_URL", "/predictions/")
    rel = path.replace("\\", "/")
    if not rel.startswith("/"):
        rel = f"{base.rstrip('/')}/{rel.lstrip('/')}"
    if request is None:
        return rel
    return request.build_absolute_uri(rel)


def _prediction_interval_for_frequency(frequency: str) -> str:
    return "1h" if frequency == "hourly" else "1d"


def _forecast_delta_for_frequency(frequency: str) -> timedelta:
    if frequency == "hourly":
        return timedelta(hours=1)
    if frequency == "weekly":
        return timedelta(days=7)
    if frequency == "monthly":
        return timedelta(days=30)
    return timedelta(days=1)


def _format_timestamp(ts: pd.Timestamp, frequency: str) -> str:
    return ts.strftime("%Y-%m-%d %H:%M") if frequency == "hourly" else ts.strftime("%Y-%m-%d")


def _history_coverage_days(row: dict[str, Any] | None) -> int:
    if not row or not row.get("min_date") or not row.get("max_date"):
        return 0
    return max((row["max_date"] - row["min_date"]).days + 1, 0)


def _max_period_for_coverage(coverage_days: int) -> str | None:
    supported = [item for item in HISTORICAL_PERIOD_OPTIONS if coverage_days >= item["days"]]
    return supported[-1]["value"] if supported else None


def _available_frequencies_for_period(max_period: str | None) -> list[str]:
    if not max_period:
        return []
    return ["daily", "weekly", "monthly"]


def _historical_period_payload() -> list[dict[str, Any]]:
    return [
        {"value": item["value"], "label": item["label"], "days": item["days"]}
        for item in HISTORICAL_PERIOD_OPTIONS
    ]


def _build_data_coverage_map(model) -> dict[str, dict[str, Any]]:
    rows = (
        model.objects.values("ticker")
        .annotate(
            row_count=Count("id"),
            min_date=Min("date"),
            max_date=Max("date"),
        )
    )
    return {row["ticker"]: dict(row) for row in rows}


def _validate_params(
    stock_symbol: str,
    model_type: str,
    prediction_frequency: str,
    historical_period: str,
) -> tuple[str, str, str, str]:
    symbol = str(stock_symbol or "").strip().upper()
    model = str(model_type or "").strip().lower()
    frequency = str(prediction_frequency or "").strip().lower()
    period = str(historical_period or "").strip().lower()

    if not symbol:
        raise ValueError("Stock symbol is required.")
    if model not in MODEL_TYPES:
        raise ValueError("Model must be one of: xgboost, lstm.")
    if frequency not in PREDICTION_FREQUENCIES:
        raise ValueError("Prediction frequency must be one of: daily, weekly, monthly.")
    if period not in HISTORICAL_PERIODS:
        raise ValueError("Historical period must be one of: 6mo, 1y, 2y, 5y.")
    if frequency == "hourly" and period == "5y":
        raise ValueError("Hourly prediction supports up to 2y. Choose 6mo, 1y, or 2y.")
    return symbol, model, frequency, period


def _series_from_history(symbol: str, period: str, frequency: str) -> pd.Series:
    from analytics.data_access import get_silver_history
    days_map = {
        "6mo": 180,
        "1y": 365,
        "2y": 730,
        "5y": 1825,
    }
    days = days_map.get(period, 365)
    df = get_silver_history(symbol, days=days)
    if df.empty:
        return pd.Series(dtype="float64")
    
    # Use 'date' as the index and extract the 'close' series
    df = df.set_index("date")
    closes = df["close"].dropna().astype("float64")
    closes.name = "close"
    return closes


def _build_feature_frame(close_series: pd.Series) -> pd.DataFrame:
    if not isinstance(close_series, pd.Series):
        close_series = pd.Series(close_series)
    df = pd.DataFrame({"close": close_series})
    df["returns_1d"] = df["close"].pct_change()
    df["sma_5"] = df["close"].rolling(window=5).mean()
    df["sma_10"] = df["close"].rolling(window=10).mean()
    df["sma_20"] = df["close"].rolling(window=20).mean()
    df["ema_12"] = df["close"].ewm(span=12, adjust=False).mean()
    df["ema_26"] = df["close"].ewm(span=26, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
    loss = -delta.where(delta < 0, 0.0).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    df["volatility_10"] = df["returns_1d"].rolling(window=10).std()
    return df


@dataclass
class ModelResult:
    forecast_dates: list[str]
    forecast_prices: list[float]
    actual_dates: list[str]
    actual_prices: list[float]
    predicted_prices: list[float]
    training_metrics: dict[str, Any]
    feature_importance: list[dict[str, Any]]
    training_loss: list[float]
    validation_loss: list[float]


def _fit_xgboost(feature_df: pd.DataFrame, frequency: str) -> ModelResult:
    try:
        from xgboost import XGBRegressor
    except Exception as exc:
        raise RuntimeError("xgboost is not installed. Install xgboost to run this model.") from exc

    supervised = feature_df.copy()
    supervised["target"] = supervised["close"].shift(-1)
    supervised = supervised.dropna().copy()
    if len(supervised) < 120:
        raise RuntimeError("Not enough historical rows for XGBoost training.")

    x = supervised[FEATURE_COLUMNS]
    y = supervised["target"]

    split_idx = int(len(supervised) * 0.8)
    x_train, x_test = x.iloc[:split_idx], x.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    test_dates = supervised.index[split_idx:]

    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_test_scaled = scaler.transform(x_test)

    model = XGBRegressor(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="reg:squarederror",
        random_state=42,
    )
    model.fit(x_train_scaled, y_train)
    pred_test = model.predict(x_test_scaled)

    mae = float(mean_absolute_error(y_test, pred_test))
    rmse = float(np.sqrt(mean_squared_error(y_test, pred_test)))
    r2 = float(r2_score(y_test, pred_test))

    step_delta = _forecast_delta_for_frequency(frequency)
    horizon = FORECAST_POINTS[frequency]
    close_series = feature_df["close"].copy()
    forecast_dates: list[str] = []
    forecast_prices: list[float] = []

    for _ in range(horizon):
        recent_chunk = close_series.tail(200)
        latest_features = _build_feature_frame(recent_chunk).dropna().iloc[-1][FEATURE_COLUMNS]
        latest_scaled = scaler.transform(pd.DataFrame([latest_features], columns=FEATURE_COLUMNS))
        next_close = float(model.predict(latest_scaled)[0])
        next_date = close_series.index[-1] + step_delta
        close_series.loc[next_date] = next_close
        forecast_dates.append(_format_timestamp(next_date, frequency))
        forecast_prices.append(round(next_close, 2))

    importances = getattr(model, "feature_importances_", None)
    feature_importance = []
    if importances is not None:
        feature_importance = [
            {"feature": col, "importance": float(score)}
            for col, score in zip(FEATURE_COLUMNS, importances)
        ]
        feature_importance.sort(key=lambda row: row["importance"], reverse=True)

    return ModelResult(
        forecast_dates=forecast_dates,
        forecast_prices=forecast_prices,
        actual_dates=[_format_timestamp(d, frequency) for d in test_dates],
        actual_prices=[round(float(v), 2) for v in y_test.to_numpy()],
        predicted_prices=[round(float(v), 2) for v in pred_test],
        training_metrics={"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4)},
        feature_importance=feature_importance,
        training_loss=[],
        validation_loss=[],
    )


def _fit_lstm(feature_df: pd.DataFrame, frequency: str) -> ModelResult:
    try:
        from tensorflow.keras.callbacks import EarlyStopping
        from tensorflow.keras.layers import LSTM, Dense, Dropout
        from tensorflow.keras.models import Sequential
    except Exception as exc:
        raise RuntimeError(
            "tensorflow is not installed. Install tensorflow to run the LSTM model."
        ) from exc

    data = feature_df[FEATURE_COLUMNS].dropna().copy()
    if frequency == "hourly" and len(data) > 3000:
        data = data.tail(3000).copy()
    if len(data) < 140:
        raise RuntimeError("Not enough historical rows for LSTM training.")

    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(data)
    seq_len = 30
    x_seq: list[np.ndarray] = []
    y_seq: list[float] = []
    target_dates: list[pd.Timestamp] = []

    for idx in range(seq_len, len(scaled)):
        x_seq.append(scaled[idx - seq_len : idx])
        y_seq.append(float(scaled[idx, 0]))
        target_dates.append(data.index[idx])

    x_all = np.array(x_seq)
    y_all = np.array(y_seq)
    if len(x_all) < 80:
        raise RuntimeError("Insufficient sequence data for LSTM.")

    split_idx = int(len(x_all) * 0.8)
    x_train, x_test = x_all[:split_idx], x_all[split_idx:]
    y_train, y_test = y_all[:split_idx], y_all[split_idx:]
    test_dates = target_dates[split_idx:]

    model = Sequential(
        [
            LSTM(64, return_sequences=True, input_shape=(x_train.shape[1], x_train.shape[2])),
            Dropout(0.2),
            LSTM(32),
            Dense(1),
        ]
    )
    model.compile(optimizer="adam", loss="mse")
    callbacks = [EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True)]
    print(
        f"[PricePrediction][LSTM] Training start | samples={len(x_train)} "
        f"val_split=0.1 epochs=10 batch_size=32 frequency={frequency}"
    )
    history = model.fit(
        x_train,
        y_train,
        epochs=10,
        batch_size=32,
        validation_split=0.1,
        callbacks=callbacks,
        verbose=1,
    )
    print("[PricePrediction][LSTM] Training complete.")

    pred_scaled = model.predict(x_test, verbose=0).reshape(-1)
    pred_close = scaler.inverse_transform(
        np.column_stack([pred_scaled, np.zeros((len(pred_scaled), len(FEATURE_COLUMNS) - 1))])
    )[:, 0]
    true_close = scaler.inverse_transform(
        np.column_stack([y_test, np.zeros((len(y_test), len(FEATURE_COLUMNS) - 1))])
    )[:, 0]

    mae = float(mean_absolute_error(true_close, pred_close))
    rmse = float(np.sqrt(mean_squared_error(true_close, pred_close)))
    r2 = float(r2_score(true_close, pred_close))

    close_series = feature_df["close"].copy()
    seq = scaled[-seq_len:].copy()
    step_delta = _forecast_delta_for_frequency(frequency)
    horizon = FORECAST_POINTS[frequency]
    forecast_dates: list[str] = []
    forecast_prices: list[float] = []

    for _ in range(horizon):
        next_tensor = model(seq[np.newaxis, :, :], training=False)
        next_scaled = float(next_tensor[0][0])
        
        dummy_df = pd.DataFrame(
            [[next_scaled] + [0.0] * (len(FEATURE_COLUMNS) - 1)],
            columns=FEATURE_COLUMNS,
        )
        next_close = float(scaler.inverse_transform(dummy_df)[0][0])
        next_date = close_series.index[-1] + step_delta
        close_series.loc[next_date] = next_close

        recent_chunk = close_series.tail(200)
        refreshed = _build_feature_frame(recent_chunk)[FEATURE_COLUMNS].dropna().iloc[-1]
        
        refreshed_df = pd.DataFrame([refreshed.to_numpy(dtype=float)], columns=FEATURE_COLUMNS)
        refreshed_scaled = scaler.transform(refreshed_df)[0]
        
        seq = np.vstack([seq[1:], refreshed_scaled])

        forecast_dates.append(_format_timestamp(next_date, frequency))
        forecast_prices.append(round(next_close, 2))

    return ModelResult(
        forecast_dates=forecast_dates,
        forecast_prices=forecast_prices,
        actual_dates=[_format_timestamp(d, frequency) for d in test_dates],
        actual_prices=[round(float(v), 2) for v in true_close],
        predicted_prices=[round(float(v), 2) for v in pred_close],
        training_metrics={"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4)},
        feature_importance=[],
        training_loss=[float(v) for v in history.history.get("loss", [])],
        validation_loss=[float(v) for v in history.history.get("val_loss", [])],
    )


def _save_history_plot(symbol: str, model: str, dates: list[str], prices: list[float]) -> str:
    plt = _get_plt()
    filename = "historical_price.png"
    abs_path = _plot_abs_path(symbol, model, filename)
    plt.figure(figsize=(11, 4))
    plt.plot(dates, prices, color="#2563eb", linewidth=1.6)
    plt.title(f"{symbol} Historical Price")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.xticks(rotation=35, ha="right")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(abs_path, dpi=140)
    plt.close()
    return _plot_rel_path(symbol, model, filename)


def _save_prediction_plot(
    symbol: str,
    model: str,
    dates: list[str],
    actual_prices: list[float],
    predicted_prices: list[float],
) -> str:
    plt = _get_plt()
    filename = "prediction_plot.png"
    abs_path = _plot_abs_path(symbol, model, filename)
    plt.figure(figsize=(11, 4))
    plt.plot(dates, actual_prices, label="Actual", color="#0f766e", linewidth=1.8)
    plt.plot(dates, predicted_prices, label="Predicted", color="#dc2626", linewidth=1.6)
    plt.title(f"{symbol} Prediction vs Actual")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.xticks(rotation=35, ha="right")
    plt.legend()
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(abs_path, dpi=140)
    plt.close()
    return _plot_rel_path(symbol, model, filename)


def _save_forecast_plot(
    symbol: str,
    model: str,
    recent_dates: list[str],
    recent_prices: list[float],
    forecast_dates: list[str],
    forecast_prices: list[float],
) -> str:
    plt = _get_plt()
    filename = "forecast_plot.png"
    abs_path = _plot_abs_path(symbol, model, filename)
    plt.figure(figsize=(11, 4))
    plt.plot(recent_dates, recent_prices, color="#2563eb", linewidth=1.8, label="Recent Price")
    plt.plot(forecast_dates, forecast_prices, linestyle="--", color="#dc2626", linewidth=1.8, label="Forecast")
    plt.title(f"{symbol} Forecast")
    plt.xlabel("Time")
    plt.ylabel("Price")
    plt.xticks(rotation=35, ha="right")
    plt.legend()
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(abs_path, dpi=140)
    plt.close()
    return _plot_rel_path(symbol, model, filename)


def _save_feature_importance_plot(symbol: str, model: str, rows: list[dict[str, Any]]) -> str:
    plt = _get_plt()
    filename = "feature_importance.png"
    abs_path = _plot_abs_path(symbol, model, filename)
    plt.figure(figsize=(10, 4))
    if rows:
        top = rows[:8]
        plt.bar([row["feature"] for row in top], [row["importance"] for row in top], color="#2563eb")
        plt.xticks(rotation=30, ha="right")
        plt.ylabel("Importance")
        plt.title("Top Feature Importance")
    else:
        plt.text(0.5, 0.5, "Feature importance unavailable for selected model", ha="center", va="center")
        plt.axis("off")
    plt.tight_layout()
    plt.savefig(abs_path, dpi=140)
    plt.close()
    return _plot_rel_path(symbol, model, filename)


def _save_training_loss_plot(
    symbol: str,
    model: str,
    training_loss: list[float],
    validation_loss: list[float],
) -> str:
    plt = _get_plt()
    filename = "training_loss.png"
    abs_path = _plot_abs_path(symbol, model, filename)
    plt.figure(figsize=(10, 4))
    if training_loss:
        epochs = list(range(1, len(training_loss) + 1))
        plt.plot(epochs, training_loss, label="Train Loss", color="#0891b2")
        if validation_loss:
            plt.plot(epochs, validation_loss, label="Validation Loss", color="#ea580c")
        plt.xlabel("Epoch")
        plt.ylabel("Loss")
        plt.title("Training Loss")
        plt.legend()
        plt.grid(alpha=0.25)
    else:
        plt.text(0.5, 0.5, "Training loss chart available only for LSTM", ha="center", va="center")
        plt.axis("off")
    plt.tight_layout()
    plt.savefig(abs_path, dpi=140)
    plt.close()
    return _plot_rel_path(symbol, model, filename)


def _find_fresh_cache(symbol: str, model: str, frequency: str, period: str) -> PredictionResultCache | None:
    cache_hours = HOURLY_CACHE_VALID_HOURS if frequency == "hourly" else CACHE_VALID_HOURS
    threshold = timezone.now() - timedelta(hours=cache_hours)
    return (
        PredictionResultCache.objects.filter(
            stock_symbol=symbol,
            model_type=model,
            prediction_frequency=frequency,
            historical_period=period,
            generated_at__gte=threshold,
        )
        .order_by("-generated_at")
        .first()
    )


def _should_refresh_model(model_type: str) -> bool:
    state = PredictionModelState.objects.filter(model_type=model_type).first()
    if not state or not state.last_trained_at:
        return True
    refresh_window = MODEL_REFRESH_WINDOWS[model_type]
    return timezone.now() - state.last_trained_at >= refresh_window


def _mark_model_trained(model_type: str) -> None:
    PredictionModelState.objects.update_or_create(
        model_type=model_type,
        defaults={"last_trained_at": timezone.now()},
    )


def _cache_response(
    symbol: str,
    model: str,
    frequency: str,
    period: str,
    forecast_data: dict[str, Any],
    plots_path: dict[str, str],
) -> PredictionResultCache:
    with transaction.atomic():
        cached, _ = PredictionResultCache.objects.update_or_create(
            stock_symbol=symbol,
            model_type=model,
            prediction_frequency=frequency,
            historical_period=period,
            defaults={
                "generated_at": timezone.now(),
                "forecast_data": forecast_data,
                "plots_path": plots_path,
            },
        )
    return cached


def _compose_response(
    symbol: str,
    model: str,
    frequency: str,
    forecast_data: dict[str, Any],
    plots_path: dict[str, str],
    request=None,
    cache_hit: bool = False,
) -> dict[str, Any]:
    plots = {key: _build_plot_url(path, request=request) for key, path in plots_path.items()}
    return {
        "stock": symbol,
        "model": model.upper(),
        "prediction_frequency": frequency,
        "forecast_dates": forecast_data.get("forecast_dates", []),
        "forecast_prices": forecast_data.get("forecast_prices", []),
        "historical_dates": forecast_data.get("historical_dates", []),
        "historical_prices": forecast_data.get("historical_prices", []),
        "actual_dates": forecast_data.get("actual_dates", []),
        "actual_prices": forecast_data.get("actual_prices", []),
        "predicted_prices": forecast_data.get("predicted_prices", []),
        "training_metrics": forecast_data.get("training_metrics", {}),
        "plots": plots,
        "cache_hit": cache_hit,
    }


def get_prediction_options() -> dict[str, Any]:
    from pipeline.models import BronzeStockPrice, SilverCleanedPrice

    silver_map = _build_data_coverage_map(SilverCleanedPrice)
    bronze_map = _build_data_coverage_map(BronzeStockPrice)
    stocks = []
    for row in (
        StockMaster.objects.filter(is_active=True)
        .order_by("ticker")
        .values("ticker", "name", "sector", "geography")
    ):
        ticker = row["ticker"]
        source = "silver" if ticker in silver_map else "bronze" if ticker in bronze_map else ""
        source_row = silver_map.get(ticker) or bronze_map.get(ticker)
        coverage_days = _history_coverage_days(source_row)
        row_count = int(source_row.get("row_count") or 0) if source_row else 0
        max_period = _max_period_for_coverage(coverage_days)
        if row_count < 120 or not max_period:
            continue

        stocks.append(
            {
                "symbol": ticker,
                "ticker": ticker,
                "company_name": row["name"],
                "name": row["name"],
                "sector": row["sector"],
                "geography": row["geography"],
                "data_source": source,
                "history_row_count": row_count,
                "history_coverage_days": coverage_days,
                "max_historical_period": max_period,
                "available_historical_periods": [max_period],
                "available_prediction_frequencies": _available_frequencies_for_period(
                    max_period
                ),
            }
        )

    if not stocks:
        stocks = []
    return {
        "stocks": stocks,
        "historical_periods": _historical_period_payload(),
        "models": [
            {"value": "xgboost", "label": "XGBoost"},
            {"value": "lstm", "label": "LSTM"},
        ],
        "prediction_frequencies": [
            {"value": "daily", "label": "Daily prediction"},
            {"value": "weekly", "label": "Weekly prediction (7 day)"},
            {"value": "monthly", "label": "Monthly prediction (30 day)"},
        ],
    }


def run_prediction(
    stock_symbol: str,
    model_type: str,
    prediction_frequency: str,
    historical_period: str,
    request=None,
) -> dict[str, Any]:
    symbol, model, frequency, period = _validate_params(
        stock_symbol=stock_symbol,
        model_type=model_type,
        prediction_frequency=prediction_frequency,
        historical_period=historical_period,
    )

    cached = _find_fresh_cache(symbol=symbol, model=model, frequency=frequency, period=period)
    if cached:
        return _compose_response(
            symbol=symbol,
            model=model,
            frequency=frequency,
            forecast_data=cached.forecast_data,
            plots_path=cached.plots_path,
            request=request,
            cache_hit=True,
        )

    close_series = _series_from_history(symbol=symbol, period=period, frequency=frequency)
    if len(close_series) < 120:
        raise RuntimeError("Insufficient historical data returned from the database.")

    feature_df = _build_feature_frame(close_series).dropna().copy()
    if feature_df.empty or len(feature_df) < 100:
        raise RuntimeError("Unable to build sufficient features from historical data.")

    if model == "xgboost":
        model_result = _fit_xgboost(feature_df=feature_df, frequency=frequency)
    else:
        model_result = _fit_lstm(feature_df=feature_df, frequency=frequency)

    model_recently_retrained = not _should_refresh_model(model)
    _mark_model_trained(model)

    history_dates = [_format_timestamp(idx, frequency) for idx in close_series.index]
    history_prices = [round(float(v), 2) for v in close_series.values]
    recent_tail = 200 if frequency == "hourly" else 120
    recent_dates = history_dates[-recent_tail:]
    recent_prices = history_prices[-recent_tail:]

    plots_path = {
        "historical_plot": _save_history_plot(symbol, model, history_dates, history_prices),
        "prediction_plot": _save_prediction_plot(
            symbol,
            model,
            model_result.actual_dates,
            model_result.actual_prices,
            model_result.predicted_prices,
        ),
        "forecast_plot": _save_forecast_plot(
            symbol,
            model,
            recent_dates,
            recent_prices,
            model_result.forecast_dates,
            model_result.forecast_prices,
        ),
        "feature_importance": _save_feature_importance_plot(
            symbol,
            model,
            model_result.feature_importance,
        ),
        "training_loss": _save_training_loss_plot(
            symbol,
            model,
            model_result.training_loss,
            model_result.validation_loss,
        ),
    }

    forecast_data = {
        "forecast_dates": model_result.forecast_dates,
        "forecast_prices": model_result.forecast_prices,
        "historical_dates": history_dates,
        "historical_prices": history_prices,
        "actual_dates": model_result.actual_dates,
        "actual_prices": model_result.actual_prices,
        "predicted_prices": model_result.predicted_prices,
        "training_metrics": {
            **model_result.training_metrics,
            "feature_importance": model_result.feature_importance,
            "training_loss": model_result.training_loss,
            "validation_loss": model_result.validation_loss,
            "retrained_now": not model_recently_retrained,
        },
    }
    forecast_json_path = _save_forecast_json(symbol=symbol, model=model, payload=forecast_data)
    forecast_data["forecast_data_path"] = forecast_json_path

    _cache_response(
        symbol=symbol,
        model=model,
        frequency=frequency,
        period=period,
        forecast_data=forecast_data,
        plots_path=plots_path,
    )
    return _compose_response(
        symbol=symbol,
        model=model,
        frequency=frequency,
        forecast_data=forecast_data,
        plots_path=plots_path,
        request=request,
        cache_hit=False,
    )


def warm_prediction_models(symbols: list[str] | None = None, model: str | None = None) -> dict[str, Any]:
    selected_models = [model.lower()] if model else ["xgboost", "lstm"]
    symbols_to_use = [s.strip().upper() for s in (symbols or []) if s.strip()]
    if not symbols_to_use:
        symbols_to_use = list(
            StockMaster.objects.filter(is_active=True)
            .order_by("ticker")
            .values_list("ticker", flat=True)[:5]
        )
    if not symbols_to_use:
        symbols_to_use = ["AAPL"]

    report: dict[str, Any] = {"ok": [], "errors": []}
    for model_type in selected_models:
        if model_type not in MODEL_TYPES:
            report["errors"].append(f"Unsupported model '{model_type}'.")
            continue
        for symbol in symbols_to_use:
            try:
                run_prediction(
                    stock_symbol=symbol,
                    model_type=model_type,
                    prediction_frequency="daily",
                    historical_period="1y",
                    request=None,
                )
                report["ok"].append(f"{model_type}:{symbol}")
            except Exception as exc:
                report["errors"].append(f"{model_type}:{symbol} -> {exc}")
    return report
