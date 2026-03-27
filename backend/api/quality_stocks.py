import json
import logging
import threading
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, TypedDict

from django.db import transaction
from django.db.models import Max, Min, OuterRef, Subquery
from django.utils import timezone

from analytics.data_access import (
    get_fundamentals_bulk,
    get_latest_forecasts_bulk,
    get_latest_prices_bulk,
    get_latest_signals_bulk,
    get_stocks_sentiment_bulk,
)
from api.chatbot_service import _call_chat_model
from pipeline.models import BronzeStockFundamentals, SilverCleanedPrice
from portfolio.models import Portfolio, PortfolioStock, QualityStock, Stock, StockMaster

logger = logging.getLogger(__name__)

try:
    from langgraph.graph import END, StateGraph

    QUALITY_LANGGRAPH_AVAILABLE = True
except Exception as exc:
    logger.debug("Quality stock LangGraph unavailable; using sequential fallback: %s", exc)
    QUALITY_LANGGRAPH_AVAILABLE = False


QUALITY_STOCK_SYSTEM_PROMPT = """You are a professional equity research analyst. You will be given financial data for one or more stocks. 
For each stock:
1. Analyze revenue growth, EPS, PE ratio, ROE, debt-to-equity, price momentum, and volume trends.
2. Assign a Quality Rating from 0 to 10 based strictly on fundamentals and momentum. Be precise — do not round to 5 or 10.
3. Give a BUY, HOLD, or SELL recommendation with a clear 3–4 sentence justification.
4. Identify the top 2 risks for this stock.
5. Identify the top 2 growth catalysts.
6. Return your response strictly as structured JSON — no prose outside the JSON.
Return format:
{
  "symbol": "...",
  "ai_rating": 7.4,
  "signal": "BUY",
  "justification": "...",
  "risks": ["...", "..."],
  "catalysts": ["...", "..."],
  "key_metrics_summary": "..."
}"""

_QUALITY_GRAPH = None
_QUALITY_GRAPH_LOCK = threading.Lock()


class QualityState(TypedDict, total=False):
    portfolio_id: int
    stock_ids: List[int]
    selected_by_user: bool
    stock_payloads: List[Dict[str, Any]]
    analyses: List[Dict[str, Any]]
    saved_rows: List[Dict[str, Any]]


def _to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_billions(value: Any) -> Optional[float]:
    numeric = _to_float(value)
    if numeric is None:
        return None
    return round(numeric / 1_000_000_000, 4)


def _normalize_signal(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "BUY" in text:
        return "BUY"
    if "SELL" in text or "REDUCE" in text:
        return "SELL"
    if "HOLD" in text:
        return "HOLD"
    return "HOLD"


def _latest_fundamental_rows(tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    if not tickers:
        return {}

    latest_subquery = (
        BronzeStockFundamentals.objects
        .filter(ticker=OuterRef("ticker"))
        .order_by("-fetched_at")
        .values("fetched_at")[:1]
    )

    rows = (
        BronzeStockFundamentals.objects
        .filter(ticker__in=tickers, fetched_at=Subquery(latest_subquery))
        .values(
            "ticker",
            "company",
            "sector",
            "geography",
            "trailing_pe",
            "forward_pe",
            "price_to_book",
            "profit_margin",
            "operating_margin",
            "gross_margin",
            "return_on_equity",
            "return_on_assets",
            "revenue_growth",
            "earnings_growth",
            "eps_trailing",
            "eps_forward",
            "market_cap",
            "total_revenue",
            "free_cashflow",
            "debt_to_equity",
            "current_ratio",
            "beta",
            "week52_high",
            "week52_low",
            "dividend_yield",
            "fetched_at",
        )
    )
    return {row["ticker"]: dict(row) for row in rows}


def _serialize_price_history(history_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output = []
    for row in history_rows[-90:]:
        row_date = row.get("date")
        output.append(
            {
                "date": row_date.isoformat() if hasattr(row_date, "isoformat") else str(row_date),
                "price": _to_float(row.get("close")),
                "volume": _to_float(row.get("volume")),
            }
        )
    return output


def _trend_metrics(history_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    prices = [_to_float(row.get("close")) for row in history_rows if _to_float(row.get("close")) is not None]
    volumes = [_to_float(row.get("volume")) for row in history_rows if _to_float(row.get("volume")) is not None]

    momentum_30d = None
    momentum_90d = None
    if len(prices) >= 31 and prices[-31] not in (None, 0):
        momentum_30d = ((prices[-1] - prices[-31]) / prices[-31]) * 100
    if len(prices) >= 90 and prices[-90] not in (None, 0):
        momentum_90d = ((prices[-1] - prices[-90]) / prices[-90]) * 100

    avg_volume_20d = None
    volume_trend_pct = None
    if volumes:
        trailing = volumes[-20:] if len(volumes) >= 20 else volumes
        baseline = volumes[-60:-20] if len(volumes) >= 60 else volumes[:-20]
        avg_volume_20d = sum(trailing) / len(trailing)
        if baseline:
            baseline_avg = sum(baseline) / len(baseline)
            if baseline_avg:
                volume_trend_pct = ((avg_volume_20d - baseline_avg) / baseline_avg) * 100

    return {
        "momentum_30d": momentum_30d,
        "momentum_90d": momentum_90d,
        "avg_volume_20d": avg_volume_20d,
        "volume_trend_pct": volume_trend_pct,
    }


def _score_snapshot_row(row: Dict[str, Any]) -> float:
    expected_change = _to_float(row.get("expected_change_pct")) or -999.0
    pe_ratio = _to_float(row.get("pe_ratio"))
    pe_bonus = 0.0 if pe_ratio in (None, 0) else max(0.0, 40.0 - min(pe_ratio, 40.0))
    momentum = _to_float(row.get("momentum_30d")) or 0.0
    signal = _normalize_signal(row.get("recommended_action"))
    signal_bonus = {"BUY": 20.0, "HOLD": 8.0, "SELL": -10.0}.get(signal, 0.0)
    return (expected_change * 2.0) + pe_bonus + momentum + signal_bonus


def _sector_average_metrics(sector: str, geography: str) -> Dict[str, Optional[float]]:
    if not sector:
        return {"revenue": None, "eps": None, "pe": None, "roe": None}

    sector_tickers = list(
        StockMaster.objects
        .filter(sector=sector, geography=geography or "IN", is_active=True)
        .values_list("ticker", flat=True)[:80]
    )
    rows = _latest_fundamental_rows(sector_tickers)
    if not rows:
        return {"revenue": None, "eps": None, "pe": None, "roe": None}

    def avg(key: str) -> Optional[float]:
        values = [_to_float(row.get(key)) for row in rows.values()]
        usable = [value for value in values if value is not None]
        if not usable:
            return None
        return round(sum(usable) / len(usable), 4)

    return {
        "revenue": avg("total_revenue"),
        "eps": avg("eps_trailing"),
        "pe": avg("trailing_pe"),
        "roe": avg("return_on_equity"),
    }


def _build_graphs_data(symbol: str, fundamentals: Dict[str, Any], history_rows: List[Dict[str, Any]], sector_avg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "price_history": _serialize_price_history(history_rows),
        "financial_metrics": [
            {
                "metric": "Revenue (B)",
                "stock_value": _to_billions(fundamentals.get("total_revenue")),
                "sector_average": _to_billions(sector_avg.get("revenue")),
                "unit": "B",
            },
            {
                "metric": "EPS",
                "stock_value": _to_float(fundamentals.get("eps_trailing")),
                "sector_average": _to_float(sector_avg.get("eps")),
            },
            {
                "metric": "PE",
                "stock_value": _to_float(fundamentals.get("trailing_pe")),
                "sector_average": _to_float(sector_avg.get("pe")),
            },
            {
                "metric": "ROE",
                "stock_value": _to_float(fundamentals.get("return_on_equity")),
                "sector_average": _to_float(sector_avg.get("roe")),
            },
        ],
        "generated_for": symbol,
    }


def _normalize_graphs_data_units(graphs_data: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(graphs_data or {})
    metrics = payload.get("financial_metrics")
    if not isinstance(metrics, list):
        return payload

    normalized_metrics = []
    for row in metrics:
        if not isinstance(row, dict):
            normalized_metrics.append(row)
            continue

        metric_name = str(row.get("metric") or "")
        normalized_row = dict(row)
        if metric_name.strip().lower() == "revenue":
            stock_value = _to_float(row.get("stock_value"))
            sector_value = _to_float(row.get("sector_average"))
            normalized_row["metric"] = "Revenue (B)"
            normalized_row["stock_value"] = _to_billions(stock_value)
            normalized_row["sector_average"] = _to_billions(sector_value)
            normalized_row["unit"] = "B"
        normalized_metrics.append(normalized_row)

    payload["financial_metrics"] = normalized_metrics
    return payload


def _deterministic_quality_report(stock_payload: Dict[str, Any]) -> Dict[str, Any]:
    fundamentals = stock_payload.get("fundamentals") or {}
    trends = stock_payload.get("trend_metrics") or {}
    signal = _normalize_signal(stock_payload.get("market_signal"))

    positive = 0.0
    negative = 0.0

    revenue_growth = _to_float(fundamentals.get("revenue_growth"))
    if revenue_growth is not None:
        positive += max(min(revenue_growth * 12, 2.5), -1.0)

    roe = _to_float(fundamentals.get("return_on_equity"))
    if roe is not None:
        positive += max(min(roe * 10, 2.0), -1.0)

    eps = _to_float(fundamentals.get("eps_trailing"))
    if eps is not None:
        positive += max(min(eps / 10, 1.5), -0.5)

    pe_ratio = _to_float(fundamentals.get("trailing_pe"))
    if pe_ratio is not None:
        positive += max(min((35 - min(pe_ratio, 35)) / 10, 1.5), -1.0)

    debt_to_equity = _to_float(fundamentals.get("debt_to_equity"))
    if debt_to_equity is not None:
        negative += max(min(debt_to_equity / 100, 1.5), 0.0)

    momentum_90d = _to_float(trends.get("momentum_90d"))
    if momentum_90d is not None:
        positive += max(min(momentum_90d / 15, 1.75), -1.0)

    volume_trend_pct = _to_float(trends.get("volume_trend_pct"))
    if volume_trend_pct is not None:
        positive += max(min(volume_trend_pct / 30, 1.0), -0.5)

    signal_bias = {"BUY": 0.9, "HOLD": 0.2, "SELL": -0.8}.get(signal, 0.0)
    score = min(9.7, max(1.5, 5.8 + positive - negative + signal_bias))
    rounded_score = round(score, 1)

    if rounded_score >= 7.2 and signal != "SELL":
        recommendation = "BUY"
    elif rounded_score <= 4.8 or signal == "SELL":
        recommendation = "SELL"
    else:
        recommendation = "HOLD"

    risks = []
    catalysts = []
    if pe_ratio is not None and pe_ratio > 28:
        risks.append("Valuation is stretched relative to a typical quality entry point.")
    if debt_to_equity is not None and debt_to_equity > 120:
        risks.append("Balance-sheet leverage is elevated and could pressure future flexibility.")
    if momentum_90d is not None and momentum_90d < 0:
        risks.append("Recent price momentum is negative, which can delay upside realization.")
    if volume_trend_pct is not None and volume_trend_pct < -10:
        risks.append("Falling trading volume suggests weaker conviction behind the trend.")
    if not risks:
        risks = [
            "Sector sentiment or macro conditions could compress valuation multiples.",
            "Execution misses would quickly weaken current momentum assumptions.",
        ]

    if revenue_growth is not None and revenue_growth > 0:
        catalysts.append("Revenue growth remains positive and supports ongoing earnings leverage.")
    if roe is not None and roe > 0.12:
        catalysts.append("Strong return on equity points to efficient capital deployment.")
    if momentum_90d is not None and momentum_90d > 0:
        catalysts.append("Positive price momentum keeps buyers engaged and supports trend continuation.")
    if volume_trend_pct is not None and volume_trend_pct > 5:
        catalysts.append("Rising trading volume signals improving market participation.")
    if len(catalysts) < 2:
        catalysts.extend(
            [
                "Steady profitability gives management room to invest through the cycle.",
                "Any earnings beat could reinforce both momentum and quality perception.",
            ]
        )

    justification = (
        f"{stock_payload.get('company_name') or stock_payload.get('symbol')} shows "
        f"{'healthy' if rounded_score >= 7 else 'mixed'} quality characteristics with revenue growth at "
        f"{revenue_growth if revenue_growth is not None else 'n/a'} and ROE at {roe if roe is not None else 'n/a'}. "
        f"Momentum over 90 days is {momentum_90d if momentum_90d is not None else 'n/a'}%, while the market signal is {signal}. "
        f"Debt-to-equity stands at {debt_to_equity if debt_to_equity is not None else 'n/a'}, which matters for downside resilience. "
        f"Overall, the current mix of fundamentals and momentum supports a {recommendation} stance."
    )

    summary = (
        f"Revenue growth={revenue_growth if revenue_growth is not None else 'n/a'}, "
        f"EPS={eps if eps is not None else 'n/a'}, "
        f"PE={pe_ratio if pe_ratio is not None else 'n/a'}, "
        f"ROE={roe if roe is not None else 'n/a'}, "
        f"Debt/Equity={debt_to_equity if debt_to_equity is not None else 'n/a'}, "
        f"Momentum90d={momentum_90d if momentum_90d is not None else 'n/a'}."
    )

    return {
        "symbol": stock_payload.get("symbol"),
        "ai_rating": rounded_score,
        "signal": recommendation,
        "justification": justification,
        "risks": risks[:2],
        "catalysts": catalysts[:2],
        "key_metrics_summary": summary,
    }


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        lines = [line for line in raw.splitlines() if not line.strip().startswith("```")]
        raw = "\n".join(lines).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_make_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


def _run_llm_quality_report(stock_payload: Dict[str, Any]) -> Dict[str, Any]:
    user_message = json.dumps(
        _make_json_safe(
            {
                "stocks": [
                    {
                        "symbol": stock_payload.get("symbol"),
                        "company_name": stock_payload.get("company_name"),
                        "sector": stock_payload.get("sector"),
                        "geography": stock_payload.get("geography"),
                        "current_price": stock_payload.get("current_price"),
                        "predicted_price": stock_payload.get("predicted_price"),
                        "expected_change_pct": stock_payload.get("expected_change_pct"),
                        "market_signal": stock_payload.get("market_signal"),
                        "fundamentals": stock_payload.get("fundamentals"),
                        "trend_metrics": stock_payload.get("trend_metrics"),
                    }
                ]
            }
        ),
        ensure_ascii=True,
    )
    try:
        response_text = _call_chat_model(QUALITY_STOCK_SYSTEM_PROMPT, [], user_message)
        parsed = _extract_json_object(response_text)
        if not parsed:
            raise ValueError("LLM response was not valid JSON.")
        parsed.setdefault("symbol", stock_payload.get("symbol"))
        parsed["signal"] = _normalize_signal(parsed.get("signal"))
        parsed["ai_rating"] = round(float(parsed.get("ai_rating")), 1)
        parsed["risks"] = list(parsed.get("risks") or [])[:2]
        parsed["catalysts"] = list(parsed.get("catalysts") or [])[:2]
        return parsed
    except Exception as exc:
        logger.warning("Quality stock LLM generation failed for %s: %s", stock_payload.get("symbol"), exc)
        return _deterministic_quality_report(stock_payload)


def _ensure_stock_record(portfolio: Portfolio, row: Dict[str, Any], latest_price: Optional[float]) -> Stock:
    stock, _ = Stock.objects.update_or_create(
        symbol=row["ticker"],
        defaults={
            "portfolio": portfolio,
            "company_name": row.get("company_name") or row["ticker"],
            "sector": row.get("sector") or portfolio.name,
            "current_price": latest_price or 0.0,
            "ticker": row["ticker"],
            "name": row.get("company_name") or row["ticker"],
            "geography": row.get("geography") or portfolio.geography or "IN",
        },
    )
    return stock


def _portfolio_market_rows(portfolio: Portfolio) -> List[Dict[str, Any]]:
    rows = list(
        PortfolioStock.objects
        .filter(portfolio=portfolio)
        .values("ticker", "company_name", "sector", "geography")
        .order_by("ticker")
    )
    if not rows:
        return []

    tickers = [row["ticker"] for row in rows]
    prices_map = get_latest_prices_bulk(tickers)
    forecast_map = get_latest_forecasts_bulk(tickers)
    signal_map = get_latest_signals_bulk(tickers)
    sentiment_map = get_stocks_sentiment_bulk(tickers)
    fundamentals_map = _latest_fundamental_rows(tickers)

    cutoff = date.today() - timedelta(days=120)
    history_qs = (
        SilverCleanedPrice.objects
        .filter(ticker__in=tickers, date__gte=cutoff)
        .order_by("ticker", "date")
        .values("ticker", "date", "close", "volume")
    )
    history_map: Dict[str, List[Dict[str, Any]]] = {}
    for row in history_qs:
        history_map.setdefault(row["ticker"], []).append(dict(row))

    results = []
    for row in rows:
        ticker = row["ticker"]
        latest_price = _to_float(prices_map.get(ticker, {}).get("close"))
        stock = _ensure_stock_record(portfolio, row, latest_price)
        forecast = forecast_map.get(ticker, {})
        signal = signal_map.get(ticker, {})
        sentiment = sentiment_map.get(ticker, {})
        fundamentals = fundamentals_map.get(ticker, {})
        trend_metrics = _trend_metrics(history_map.get(ticker, []))
        results.append(
            {
                "stock_id": stock.id,
                "symbol": ticker,
                "company_name": row.get("company_name") or ticker,
                "sector": row.get("sector") or stock.sector,
                "geography": row.get("geography") or stock.geography,
                "current_price": latest_price,
                "predicted_price_1d": _to_float(forecast.get("predicted_price")),
                "expected_change_pct": _to_float(forecast.get("expected_change_pct")),
                "recommended_action": _normalize_signal(signal.get("signal")),
                "sentiment_score": _to_float(sentiment.get("sentiment_score")),
                "sentiment_label": sentiment.get("sentiment_label"),
                "pe_ratio": _to_float(fundamentals.get("trailing_pe")),
                "momentum_30d": _to_float(trend_metrics.get("momentum_30d")),
                "momentum_90d": _to_float(trend_metrics.get("momentum_90d")),
                "volume_trend_pct": _to_float(trend_metrics.get("volume_trend_pct")),
            }
        )
    return results


def build_quality_snapshot(portfolio: Portfolio) -> List[Dict[str, Any]]:
    candidates = _portfolio_market_rows(portfolio)
    ranked = sorted(candidates, key=_score_snapshot_row, reverse=True)
    return ranked[:3]


def _build_report_payload(portfolio: Portfolio, stock: Stock) -> Dict[str, Any]:
    symbol = stock.symbol
    fundamentals = _latest_fundamental_rows([symbol]).get(symbol, {})
    price_map = get_latest_prices_bulk([symbol])
    forecast_map = get_latest_forecasts_bulk([symbol])
    signal_map = get_latest_signals_bulk([symbol])
    history_rows = list(
        SilverCleanedPrice.objects
        .filter(ticker=symbol, date__gte=date.today() - timedelta(days=120))
        .order_by("date")
        .values("date", "close", "volume")
    )
    trend_metrics = _trend_metrics(history_rows)
    sector_avg = _sector_average_metrics(stock.sector or fundamentals.get("sector") or "", stock.geography or fundamentals.get("geography") or "IN")

    return {
        "stock_id": stock.id,
        "symbol": symbol,
        "company_name": stock.company_name,
        "sector": stock.sector,
        "geography": stock.geography,
        "current_price": _to_float(price_map.get(symbol, {}).get("close")) or _to_float(stock.current_price),
        "predicted_price": _to_float(forecast_map.get(symbol, {}).get("predicted_price")),
        "expected_change_pct": _to_float(forecast_map.get(symbol, {}).get("expected_change_pct")),
        "market_signal": _normalize_signal(signal_map.get(symbol, {}).get("signal")),
        "fundamentals": fundamentals,
        "trend_metrics": trend_metrics,
        "graphs_data": _build_graphs_data(symbol, fundamentals, history_rows, sector_avg),
        "sector_average_metrics": sector_avg,
    }


def _fetch_quality_node(state: QualityState) -> QualityState:
    portfolio = Portfolio.objects.get(id=state["portfolio_id"])
    allowed = {
        stock.id: stock
        for stock in Stock.objects.filter(
            id__in=state.get("stock_ids", []),
            symbol__in=PortfolioStock.objects.filter(portfolio=portfolio).values("ticker"),
        )
    }
    payloads = [_build_report_payload(portfolio, allowed[stock_id]) for stock_id in state.get("stock_ids", []) if stock_id in allowed]
    return {"stock_payloads": payloads}


def _analyze_quality_node(state: QualityState) -> QualityState:
    analyses = []
    for payload in state.get("stock_payloads", []):
        analyses.append(_run_llm_quality_report(payload))
    return {"analyses": analyses}


def _persist_quality_node(state: QualityState) -> QualityState:
    portfolio = Portfolio.objects.get(id=state["portfolio_id"])
    selected_by_user = bool(state.get("selected_by_user", True))
    payloads_by_id = {payload["stock_id"]: payload for payload in state.get("stock_payloads", [])}
    analyses = state.get("analyses", [])

    saved_rows = []
    with transaction.atomic():
        for analysis in analyses:
            symbol = analysis.get("symbol")
            stock = Stock.objects.filter(id__in=payloads_by_id.keys(), symbol=symbol).first()
            if not stock:
                continue
            payload = payloads_by_id[stock.id]
            quality_stock, _ = QualityStock.objects.update_or_create(
                portfolio=portfolio,
                stock=stock,
                defaults={
                    "ai_rating": _to_float(analysis.get("ai_rating")) or 0.0,
                    "buy_signal": _normalize_signal(analysis.get("signal")),
                    "report_json": analysis,
                    "graphs_data": payload.get("graphs_data") or {},
                    "generated_at": timezone.now(),
                    "selected_by_user": selected_by_user,
                },
            )
            saved_rows.append({"id": quality_stock.id, "stock_id": stock.id, "symbol": stock.symbol})
    return {"saved_rows": saved_rows}


def _get_quality_graph():
    global _QUALITY_GRAPH
    if not QUALITY_LANGGRAPH_AVAILABLE:
        return None
    if _QUALITY_GRAPH is not None:
        return _QUALITY_GRAPH

    with _QUALITY_GRAPH_LOCK:
        if _QUALITY_GRAPH is not None:
            return _QUALITY_GRAPH

        graph = StateGraph(QualityState)
        graph.add_node("fetch", _fetch_quality_node)
        graph.add_node("analyze", _analyze_quality_node)
        graph.add_node("persist", _persist_quality_node)
        graph.set_entry_point("fetch")
        graph.add_edge("fetch", "analyze")
        graph.add_edge("analyze", "persist")
        graph.add_edge("persist", END)
        _QUALITY_GRAPH = graph.compile()
        return _QUALITY_GRAPH


def generate_quality_reports(*, portfolio: Portfolio, stock_ids: List[int], selected_by_user: bool = True) -> List[Dict[str, Any]]:
    state: QualityState = {
        "portfolio_id": portfolio.id,
        "stock_ids": stock_ids,
        "selected_by_user": selected_by_user,
    }
    graph = _get_quality_graph()
    if graph is None:
        fetched = _fetch_quality_node(state)
        analyzed = _analyze_quality_node({**state, **fetched})
        persisted = _persist_quality_node({**state, **fetched, **analyzed})
        return persisted.get("saved_rows", [])

    result = graph.invoke(state)
    return result.get("saved_rows", [])


def _quality_queryset_for_user(user, portfolio_id: Optional[int] = None):
    qs = QualityStock.objects.filter(portfolio__user=user).select_related("stock", "portfolio")
    if portfolio_id:
        qs = qs.filter(portfolio_id=portfolio_id)
    return qs


def build_quality_stock_rows(user, *, portfolio_id: Optional[int] = None, signal: str = "all") -> List[Dict[str, Any]]:
    qs = _quality_queryset_for_user(user, portfolio_id=portfolio_id)
    if signal and signal.lower() != "all":
        qs = qs.filter(buy_signal=_normalize_signal(signal))

    quality_rows = list(qs.order_by("-generated_at"))
    if not quality_rows:
        return []

    symbols = [row.stock.symbol for row in quality_rows]
    tickers = list(dict.fromkeys(symbols))
    latest_prices = get_latest_prices_bulk(tickers)
    forecast_map = get_latest_forecasts_bulk(tickers)
    signal_map = get_latest_signals_bulk(tickers)
    sentiment_map = get_stocks_sentiment_bulk(tickers)
    fundamentals_map = get_fundamentals_bulk(tickers)

    cutoff = date.today() - timedelta(days=365)
    range_rows = (
        SilverCleanedPrice.objects
        .filter(ticker__in=tickers, date__gte=cutoff)
        .values("ticker")
        .annotate(week_high=Max("high"), week_low=Min("low"))
    )
    range_map = {row["ticker"]: row for row in range_rows}

    payload = []
    for row in quality_rows:
        symbol = row.stock.symbol
        latest_price = _to_float(latest_prices.get(symbol, {}).get("close")) or _to_float(row.stock.current_price)
        forecast = forecast_map.get(symbol, {})
        fundamentals = fundamentals_map.get(symbol, {})
        sentiment_row = sentiment_map.get(symbol, {})
        current_signal = signal_map.get(symbol, {})
        price_high = _to_float(range_map.get(symbol, {}).get("week_high"))
        discount_pct = None
        if latest_price not in (None, 0) and price_high not in (None, 0):
            discount_pct = round(((price_high - latest_price) / price_high) * 100, 2)

        payload.append(
            {
                "id": row.id,
                "quality_stock_id": row.id,
                "stock_id": row.stock_id,
                "portfolio_id": row.portfolio_id,
                "portfolio_name": row.portfolio.name,
                "symbol": symbol,
                "company_name": row.stock.company_name,
                "sector": row.stock.sector,
                "geography": row.stock.geography,
                "current_price": latest_price,
                "min_price": _to_float(range_map.get(symbol, {}).get("week_low")),
                "max_price": price_high,
                "predicted_price_1d": _to_float(forecast.get("predicted_price")),
                "expected_change_pct": _to_float(forecast.get("expected_change_pct")),
                "direction_signal": forecast.get("direction") or "",
                "model_confidence_r2": _to_float(forecast.get("confidence_r2")),
                "recommended_action": row.buy_signal,
                "market_signal": _normalize_signal(current_signal.get("signal")),
                "prediction_status": "ready" if forecast else "insufficient_data",
                "pe_ratio": _to_float(fundamentals.get("trailing_pe")),
                "discount_pct": discount_pct,
                "sentiment_score": _to_float(sentiment_row.get("sentiment_score")),
                "sentiment_label": sentiment_row.get("sentiment_label"),
                "ai_rating": row.ai_rating,
                "buy_signal": row.buy_signal,
                "generated_at": row.generated_at,
                "selected_by_user": row.selected_by_user,
            }
        )
    return payload


def get_quality_stock_detail(user, quality_stock_id: int) -> Optional[Dict[str, Any]]:
    quality_stock = (
        QualityStock.objects
        .filter(id=quality_stock_id, portfolio__user=user)
        .select_related("stock", "portfolio")
        .first()
    )
    if not quality_stock:
        return None

    row = build_quality_stock_rows(user, portfolio_id=quality_stock.portfolio_id, signal="all")
    list_row = next((item for item in row if item["quality_stock_id"] == quality_stock_id), None)
    if not list_row:
        list_row = {
            "id": quality_stock.id,
            "quality_stock_id": quality_stock.id,
            "stock_id": quality_stock.stock_id,
            "portfolio_id": quality_stock.portfolio_id,
            "portfolio_name": quality_stock.portfolio.name,
            "symbol": quality_stock.stock.symbol,
            "company_name": quality_stock.stock.company_name,
            "sector": quality_stock.stock.sector,
            "geography": quality_stock.stock.geography,
            "ai_rating": quality_stock.ai_rating,
            "buy_signal": quality_stock.buy_signal,
            "generated_at": quality_stock.generated_at,
        }

    symbol = quality_stock.stock.symbol
    fundamentals = _latest_fundamental_rows([symbol]).get(symbol, {})
    sector_avg = _sector_average_metrics(quality_stock.stock.sector, quality_stock.stock.geography)

    key_financials = {
        "revenue_growth": _to_float(fundamentals.get("revenue_growth")),
        "earnings_growth": _to_float(fundamentals.get("earnings_growth")),
        "eps_trailing": _to_float(fundamentals.get("eps_trailing")),
        "eps_forward": _to_float(fundamentals.get("eps_forward")),
        "trailing_pe": _to_float(fundamentals.get("trailing_pe")),
        "forward_pe": _to_float(fundamentals.get("forward_pe")),
        "price_to_book": _to_float(fundamentals.get("price_to_book")),
        "profit_margin": _to_float(fundamentals.get("profit_margin")),
        "operating_margin": _to_float(fundamentals.get("operating_margin")),
        "gross_margin": _to_float(fundamentals.get("gross_margin")),
        "return_on_equity": _to_float(fundamentals.get("return_on_equity")),
        "return_on_assets": _to_float(fundamentals.get("return_on_assets")),
        "debt_to_equity": _to_float(fundamentals.get("debt_to_equity")),
        "current_ratio": _to_float(fundamentals.get("current_ratio")),
        "market_cap": _to_float(fundamentals.get("market_cap")),
        "total_revenue": _to_float(fundamentals.get("total_revenue")),
        "beta": _to_float(fundamentals.get("beta")),
        "dividend_yield": _to_float(fundamentals.get("dividend_yield")),
        "week52_high": _to_float(fundamentals.get("week52_high")),
        "week52_low": _to_float(fundamentals.get("week52_low")),
        "sector_average_metrics": sector_avg,
    }

    report_json = quality_stock.report_json or {}
    normalized_graphs = _normalize_graphs_data_units(quality_stock.graphs_data or {})
    return {
        **list_row,
        "report_json": report_json,
        "graphs_data": normalized_graphs,
        "key_financials": key_financials,
        "justification": report_json.get("justification"),
        "risks": list(report_json.get("risks") or []),
        "catalysts": list(report_json.get("catalysts") or []),
        "key_metrics_summary": report_json.get("key_metrics_summary"),
    }
