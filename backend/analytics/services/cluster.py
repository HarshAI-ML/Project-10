from __future__ import annotations

from hashlib import sha1
from typing import Any

import numpy as np
import pandas as pd
import umap
from django.core.cache import cache
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from analytics.data_access import get_multiple_stocks_history
from portfolio.models import Stock


MIN_STOCKS = 5
MIN_HISTORY_POINTS = 220
HISTORY_VALID_RATIO = 0.70
YF_CACHE_TTL = 60 * 60 * 6
FEATURE_CACHE_TTL = 60 * 30
RESULT_CACHE_TTL = 60 * 30
CACHE_VERSION = "v4"
CLUSTER_RANGE_MIN = 2
CLUSTER_RANGE_MAX = 6

BASE_CLUSTER_LABELS = [
    "Uptrend Leaders",
    "Possible Rebound",
    "Stable Stocks",
    "Weak Stocks",
]

CLUSTER_MEANING = {
    "Uptrend Leaders": "Strong momentum with supportive trend behavior.",
    "Possible Rebound": "Oversold profile with recovery potential.",
    "Stable Stocks": "Lower volatility and steadier return profile.",
    "Weak Stocks": "Lower trend strength and weaker momentum profile.",
}

FEATURE_COLUMNS = [
    "momentum",
    "volatility",
    "dist_ma50",
    "dist_ma200",
    "trend",
    "drawdown",
    "dist_52w_high",
    "rsi",
    "beta",
]


def _history_cache_key(tickers: list[str]) -> str:
    digest = sha1(",".join(sorted(tickers)).encode("utf-8")).hexdigest()
    return f"cluster:history:{CACHE_VERSION}:{digest}"


def _feature_cache_key(portfolio_id: int, tickers: list[str]) -> str:
    digest = sha1(",".join(sorted(tickers)).encode("utf-8")).hexdigest()
    return f"cluster:features:{CACHE_VERSION}:{portfolio_id}:{digest}"


def _result_cache_key(portfolio_id: int, tickers: list[str]) -> str:
    digest = sha1(",".join(sorted(tickers)).encode("utf-8")).hexdigest()
    return f"cluster:result:{CACHE_VERSION}:{portfolio_id}:{digest}"


def _to_prices(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.get_level_values(0):
            prices = data["Close"]
        else:
            prices = data.xs(data.columns.levels[0][0], axis=1, level=0)
    elif "Close" in data.columns:
        prices = data[["Close"]]
    else:
        prices = data

    if isinstance(prices, pd.Series):
        prices = prices.to_frame(name="Close")
    prices.columns = [str(col).upper() for col in prices.columns]
    return prices.sort_index()


def _download_prices(tickers: list[str]) -> pd.DataFrame:
    cache_key = _history_cache_key(tickers)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Fetch from BronzeStockPrice (DB-only, no yfinance)
    histories = get_multiple_stocks_history(tickers, days=3 * 365)

    # Build a wide DataFrame: index=date, columns=ticker, values=close
    frames = {}
    for ticker, df in histories.items():
        if not df.empty and 'close' in df.columns:
            s = df.set_index('date')['close'].rename(ticker.upper())
            frames[ticker.upper()] = s

    if not frames:
        prices = pd.DataFrame()
        cache.set(cache_key, prices, YF_CACHE_TTL)
        return prices

    prices = pd.DataFrame(frames)
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index()

    min_non_null = max(int(len(prices.index) * HISTORY_VALID_RATIO), MIN_HISTORY_POINTS)
    prices = prices.dropna(axis=1, thresh=min_non_null)
    prices = prices.ffill(limit=3)
    prices = prices.dropna(how="all")

    cache.set(cache_key, prices, YF_CACHE_TTL)
    return prices


def _download_nifty_returns(index_like: pd.Index) -> pd.Series:
    # Fetch Nifty benchmark (^NSEI stored as NSEI in Bronze if pipeline is extended)
    # For now, fall back to a constant zero-beta if not available — clustering
    # still works; beta feature will be 0 for all stocks but the rest are valid.
    histories = get_multiple_stocks_history(['^NSEI'], days=3 * 365)
    df = histories.get('^NSEI', pd.DataFrame())
    if df.empty or 'close' not in df.columns:
        return pd.Series(dtype=float)

    benchmark = df.set_index('date')['close']
    benchmark.index = pd.to_datetime(benchmark.index)
    returns = benchmark.pct_change().dropna()
    if returns.empty:
        return pd.Series(dtype=float)
    return returns.reindex(index_like).dropna()


def _compute_rsi(prices: pd.Series, window: int = 14) -> float | None:
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    last_gain = avg_gain.iloc[-1]
    last_loss = avg_loss.iloc[-1]
    if pd.isna(last_gain) or pd.isna(last_loss):
        return None
    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
    return float(100 - (100 / (1 + rs)))


def _compute_beta(stock_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    aligned = pd.concat([stock_returns, benchmark_returns], axis=1, join="inner").dropna()
    if aligned.empty or aligned.shape[0] < 30:
        return 0.0
    cov = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
    var = aligned.iloc[:, 1].var()
    if pd.isna(cov) or pd.isna(var) or var == 0:
        return 0.0
    return float(cov / var)


def _build_feature_frame(prices: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    benchmark_returns = _download_nifty_returns(prices.index)

    for symbol in prices.columns:
        p = prices[symbol].dropna()
        if len(p) < MIN_HISTORY_POINTS:
            continue

        returns = p.pct_change().dropna()
        if len(returns) < 60:
            continue

        ma50 = p.rolling(50).mean()
        ma200 = p.rolling(200).mean()
        ma50_last = ma50.iloc[-1]
        ma200_last = ma200.iloc[-1]
        if pd.isna(ma50_last) or pd.isna(ma200_last) or ma50_last == 0 or ma200_last == 0:
            continue

        rolling_52w_high = p.rolling(252).max().iloc[-1]
        if pd.isna(rolling_52w_high) or rolling_52w_high == 0:
            continue

        price_last = p.iloc[-1]
        rsi = _compute_rsi(p, window=14)
        if rsi is None:
            continue

        row = {
            "stock": str(symbol).upper(),
            "momentum": float(p.pct_change(60).iloc[-1]),
            "volatility": float(returns.std()),
            "dist_ma50": float((price_last - ma50_last) / ma50_last),
            "dist_ma200": float((price_last - ma200_last) / ma200_last),
            "trend": float(ma50_last - ma200_last),
            "drawdown": float((p / p.cummax() - 1).min()),
            "dist_52w_high": float((price_last - rolling_52w_high) / rolling_52w_high),
            "rsi": float(rsi),
            "beta": float(_compute_beta(returns, benchmark_returns)),
        }

        if any(pd.isna(row[col]) or np.isinf(row[col]) for col in FEATURE_COLUMNS):
            continue
        rows.append(row)

    return pd.DataFrame(rows)


def _winsorize_and_zscore(features_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw_df = features_df.copy()
    norm_df = features_df.copy()

    for col in FEATURE_COLUMNS:
        lower = norm_df[col].quantile(0.05)
        upper = norm_df[col].quantile(0.95)
        norm_df[col] = norm_df[col].clip(lower=lower, upper=upper)
        std = float(norm_df[col].std(ddof=0))
        if std == 0 or pd.isna(std):
            norm_df[col] = 0.0
        else:
            norm_df[col] = (norm_df[col] - norm_df[col].mean()) / std

    return raw_df, norm_df


def _choose_kmeans_k(embedding: np.ndarray) -> int:
    n_samples = embedding.shape[0]
    max_k = min(CLUSTER_RANGE_MAX, n_samples - 1)
    min_k = min(CLUSTER_RANGE_MIN, max_k)
    if n_samples < 3:
        return 1
    if max_k < 2:
        return 1

    best_k = min_k
    best_score = -1.0
    for k in range(min_k, max_k + 1):
        try:
            model = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = model.fit_predict(embedding)
            unique_labels = np.unique(labels)
            if unique_labels.shape[0] < 2 or unique_labels.shape[0] >= n_samples:
                continue
            score = silhouette_score(embedding, labels)
            if score > best_score:
                best_score = float(score)
                best_k = k
        except Exception:
            continue
    return best_k


def _assign_cluster_names(raw_with_cluster: pd.DataFrame) -> dict[int, str]:
    summary = (
        raw_with_cluster.groupby("cluster", as_index=False)
        .agg(
            momentum=("momentum", "mean"),
            trend=("trend", "mean"),
            volatility=("volatility", "mean"),
            dist_52w_high=("dist_52w_high", "mean"),
            drawdown=("drawdown", "mean"),
            rsi=("rsi", "mean"),
        )
        .copy()
    )

    remaining = set(int(x) for x in summary["cluster"].tolist())
    mapping: dict[int, str] = {}

    if not remaining:
        return mapping

    # Stable: minimum volatility
    stable_cluster = int(summary.loc[summary["volatility"].idxmin(), "cluster"])
    mapping[stable_cluster] = "Stable Stocks"
    remaining.discard(stable_cluster)

    if remaining:
        candidate = summary[summary["cluster"].isin(list(remaining))].copy()
        candidate["lead_score"] = candidate["momentum"] + candidate["trend"] + candidate["dist_52w_high"]
        uptrend_cluster = int(candidate.loc[candidate["lead_score"].idxmax(), "cluster"])
        mapping[uptrend_cluster] = "Uptrend Leaders"
        remaining.discard(uptrend_cluster)

    if remaining:
        candidate = summary[summary["cluster"].isin(list(remaining))].copy()
        candidate["rebound_score"] = (-candidate["dist_52w_high"]) + (-candidate["rsi"] / 100.0)
        rebound_cluster = int(candidate.loc[candidate["rebound_score"].idxmax(), "cluster"])
        mapping[rebound_cluster] = "Possible Rebound"
        remaining.discard(rebound_cluster)

    for cluster_id in sorted(remaining):
        mapping[int(cluster_id)] = "Weak Stocks"

    return mapping


def build_portfolio_clusters(portfolio_id: int) -> dict[str, Any]:
    try:
        rows = list(Stock.objects.filter(portfolio_id=portfolio_id).order_by("symbol").values("symbol"))
        tickers = [str(row["symbol"]).upper() for row in rows]

        if len(tickers) < MIN_STOCKS:
            return {
                "portfolio_id": portfolio_id,
                "status": "insufficient_data",
                "detail": "Portfolio needs at least 5 stocks for clustering.",
                "stocks": tickers,
                "features": [],
                "clusters": [],
                "cluster_labels": {},
                "umap_embedding": [],
                "cluster_centers": [],
                "opportunity_scores": [],
                "top_opportunities": [],
                "cluster_summary": [],
            }

        result_key = _result_cache_key(portfolio_id, tickers)
        cached = cache.get(result_key)
        if cached is not None:
            return cached

        prices = _download_prices(tickers)
        if prices.empty or prices.shape[1] < MIN_STOCKS:
            payload = {
                "portfolio_id": portfolio_id,
                "status": "insufficient_data",
                "detail": (
                    f"Not enough valid stock price series after cleaning "
                    f"({prices.shape[1] if not prices.empty else 0}/{len(tickers)} valid; need at least {MIN_STOCKS})."
                ),
                "stocks": list(prices.columns) if not prices.empty else [],
                "features": [],
                "clusters": [],
                "cluster_labels": {},
                "umap_embedding": [],
                "cluster_centers": [],
                "opportunity_scores": [],
                "top_opportunities": [],
                "cluster_summary": [],
            }
            cache.set(result_key, payload, RESULT_CACHE_TTL)
            return payload

        feature_key = _feature_cache_key(portfolio_id, list(prices.columns))
        feature_cached = cache.get(feature_key)
        if feature_cached is None:
            features_raw = _build_feature_frame(prices)
            cache.set(feature_key, features_raw, FEATURE_CACHE_TTL)
        else:
            features_raw = feature_cached

        if features_raw.empty or len(features_raw) < MIN_STOCKS:
            payload = {
                "portfolio_id": portfolio_id,
                "status": "insufficient_data",
                "detail": "Insufficient historical data for factor computation.",
                "stocks": features_raw["stock"].tolist() if not features_raw.empty else [],
                "features": [],
                "clusters": [],
                "cluster_labels": {},
                "umap_embedding": [],
                "cluster_centers": [],
                "opportunity_scores": [],
                "top_opportunities": [],
                "cluster_summary": [],
            }
            cache.set(result_key, payload, RESULT_CACHE_TTL)
            return payload

        raw_df, norm_df = _winsorize_and_zscore(features_raw)
        scaler = StandardScaler()
        x_scaled = scaler.fit_transform(norm_df[FEATURE_COLUMNS])

        reducer = umap.UMAP(n_neighbors=10, min_dist=0.2, random_state=42)
        embedding = reducer.fit_transform(x_scaled)

        best_k = _choose_kmeans_k(embedding)
        if best_k <= 1:
            best_k = min(2, len(raw_df))

        kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
        clusters = kmeans.fit_predict(embedding)

        raw_df = raw_df.copy()
        norm_df = norm_df.copy()
        raw_df["cluster"] = clusters
        norm_df["cluster"] = clusters

        cluster_name_map = _assign_cluster_names(raw_df)
        raw_df["cluster_label"] = raw_df["cluster"].map(cluster_name_map)
        norm_df["cluster_label"] = norm_df["cluster"].map(cluster_name_map)

        # Normalize UMAP coordinates for cleaner visual separation in charts.
        vis_scaler = StandardScaler()
        embedding_vis = vis_scaler.fit_transform(embedding)
        centers_vis = vis_scaler.transform(kmeans.cluster_centers_)

        raw_df["umap_x"] = embedding_vis[:, 0]
        raw_df["umap_y"] = embedding_vis[:, 1]

        # Opportunity score on normalized factors.
        norm_df["opportunity_score"] = (
            0.4 * norm_df["momentum"]
            + 0.3 * norm_df["trend"]
            + 0.2 * norm_df["dist_52w_high"]
            - 0.1 * norm_df["volatility"]
        )
        raw_df["opportunity_score"] = norm_df["opportunity_score"]
        raw_df = raw_df.sort_values("opportunity_score", ascending=False).reset_index(drop=True)

        summary_df = (
            raw_df.groupby(["cluster", "cluster_label"], as_index=False)
            .agg(
                stock_count=("stock", "count"),
                avg_momentum=("momentum", "mean"),
                avg_volatility=("volatility", "mean"),
                avg_trend=("trend", "mean"),
                avg_opportunity=("opportunity_score", "mean"),
            )
            .sort_values("cluster")
            .reset_index(drop=True)
        )
        summary_df["description"] = summary_df["cluster_label"].map(CLUSTER_MEANING).fillna(CLUSTER_MEANING["Weak Stocks"])

        features_records = []
        for _, row in raw_df.iterrows():
            features_records.append(
                {
                    "stock": row["stock"],
                    "momentum": round(float(row["momentum"]), 6),
                    "volatility": round(float(row["volatility"]), 6),
                    "dist_ma50": round(float(row["dist_ma50"]), 6),
                    "dist_ma200": round(float(row["dist_ma200"]), 6),
                    "trend": round(float(row["trend"]), 6),
                    "drawdown": round(float(row["drawdown"]), 6),
                    "dist_52w_high": round(float(row["dist_52w_high"]), 6),
                    "rsi": round(float(row["rsi"]), 4),
                    "beta": round(float(row["beta"]), 4),
                    "cluster": int(row["cluster"]),
                    "cluster_label": row["cluster_label"],
                    "umap_x": float(row["umap_x"]),
                    "umap_y": float(row["umap_y"]),
                    "opportunity_score": round(float(row["opportunity_score"]), 6),
                }
            )

        opportunity_scores = [
            {"stock": row["stock"], "opportunity_score": round(float(row["opportunity_score"]), 6)}
            for _, row in raw_df[["stock", "opportunity_score"]].iterrows()
        ]
        top_opportunities = opportunity_scores[:10]

        payload = {
            "portfolio_id": portfolio_id,
            "status": "ok",
            "detail": "Multi-factor clustering completed.",
            "stocks": [str(v) for v in raw_df["stock"].tolist()],
            "features": features_records,
            "clusters": [int(v) for v in clusters.tolist()],
            "cluster_labels": {int(k): v for k, v in cluster_name_map.items()},
            "umap_embedding": [[float(point[0]), float(point[1])] for point in embedding_vis],
            "cluster_centers": [[float(value) for value in center] for center in centers_vis],
            "opportunity_scores": opportunity_scores,
            "top_opportunities": top_opportunities,
            "cluster_summary": [
                {
                    "cluster": int(row["cluster"]),
                    "cluster_label": row["cluster_label"],
                    "stock_count": int(row["stock_count"]),
                    "avg_momentum": float(row["avg_momentum"]),
                    "avg_volatility": float(row["avg_volatility"]),
                    "avg_trend": float(row["avg_trend"]),
                    "avg_opportunity": float(row["avg_opportunity"]),
                    "description": row["description"],
                }
                for _, row in summary_df.iterrows()
            ],
            # Backward-compatible aliases used by existing frontend code.
            "umap": [[float(point[0]), float(point[1])] for point in embedding_vis],
            "centroids": [[float(value) for value in center] for center in centers_vis],
        }
        cache.set(result_key, payload, RESULT_CACHE_TTL)
        return payload
    except Exception as exc:
        return {
            "portfolio_id": portfolio_id,
            "status": "error",
            "detail": f"Failed to generate clustering analysis: {exc}",
            "stocks": [],
            "features": [],
            "clusters": [],
            "cluster_labels": {},
            "umap_embedding": [],
            "cluster_centers": [],
            "opportunity_scores": [],
            "top_opportunities": [],
            "cluster_summary": [],
        }
