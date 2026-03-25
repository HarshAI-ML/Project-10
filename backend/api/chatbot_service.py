import os
from typing import Any, Dict, List, Optional, TypedDict
import json

import requests
from django.contrib.auth.models import AnonymousUser

from analytics.data_access import (
    get_fundamentals_bulk,
    get_latest_forecasts_bulk,
    get_latest_price,
    get_latest_signals_bulk,
    get_stocks_sentiment_bulk,
)
from portfolio.models import Portfolio, PortfolioStock

try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:
    LANGGRAPH_AVAILABLE = False


class ChatState(TypedDict, total=False):
    message: str
    history: List[Dict[str, str]]
    is_authenticated: bool
    user: Any
    route: str
    user_context: str
    response: str


def _normalize_history(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    cleaned: List[Dict[str, str]] = []
    for item in (history or [])[-10:]:
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            cleaned.append({"role": role, "content": content[:1000]})
    return cleaned


def _call_groq_chat(system_prompt: str, history: List[Dict[str, str]], user_message: str) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return "Chatbot is not configured yet. Please set GROQ_API_KEY in backend .env."

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": messages,
                "temperature": 0.35,
                "max_tokens": 450,
            },
            timeout=25,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return str(content).strip()
    except requests.exceptions.HTTPError as exc:
        status = getattr(exc.response, "status_code", "unknown")
        return f"I could not generate a response right now (model API error: {status}). Please try again."
    except Exception:
        return "I could not generate a response right now. Please try again in a moment."


def _call_openrouter_chat(system_prompt: str, history: List[Dict[str, str]], user_message: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return "OPENROUTER_API_KEY is not configured."

    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo").strip()
    app_name = os.getenv("OPENROUTER_APP_NAME", "auto-invest-chatbot").strip()

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost",
                "X-Title": app_name,
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.35,
                "max_tokens": 450,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return str(content).strip()
    except requests.exceptions.HTTPError as exc:
        status = getattr(exc.response, "status_code", "unknown")
        return f"OpenRouter request failed (HTTP {status})."
    except Exception:
        return "OpenRouter request failed."


def _call_chat_model(system_prompt: str, history: List[Dict[str, str]], user_message: str) -> str:
    """
    Provider selection:
    - CHAT_PROVIDER=openrouter => OpenRouter only
    - CHAT_PROVIDER=groq       => Groq only
    - default/auto             => Groq first, fallback to OpenRouter
    """
    provider = os.getenv("CHAT_PROVIDER", "auto").strip().lower()

    if provider == "openrouter":
        return _call_openrouter_chat(system_prompt, history, user_message)
    if provider == "groq":
        return _call_groq_chat(system_prompt, history, user_message)

    # auto fallback mode
    groq_reply = _call_groq_chat(system_prompt, history, user_message)
    if "could not generate" in groq_reply.lower() or "model api error" in groq_reply.lower() or "not configured" in groq_reply.lower():
        openrouter_reply = _call_openrouter_chat(system_prompt, history, user_message)
        if "failed" not in openrouter_reply.lower() and "not configured" not in openrouter_reply.lower():
            return openrouter_reply
    return groq_reply


def _build_user_context(user: Any) -> str:
    portfolios = list(
        Portfolio.objects.filter(user=user).values("id", "name", "geography", "is_default").order_by("-is_default", "name")
    )
    if not portfolios:
        return "User has no portfolios yet."

    portfolio_ids = [p["id"] for p in portfolios]
    stocks = list(
        PortfolioStock.objects.filter(portfolio_id__in=portfolio_ids)
        .values("portfolio_id", "ticker", "company_name", "sector", "geography")
        .order_by("portfolio_id", "ticker")
    )

    tickers = sorted({s["ticker"] for s in stocks if s.get("ticker")})[:25]
    signals = get_latest_signals_bulk(tickers) if tickers else {}
    forecasts = get_latest_forecasts_bulk(tickers) if tickers else {}
    sentiment = get_stocks_sentiment_bulk(tickers) if tickers else {}
    fundamentals = get_fundamentals_bulk(tickers) if tickers else {}

    lines: List[str] = []
    lines.append("User portfolio summary:")
    for p in portfolios:
        p_stocks = [s for s in stocks if s["portfolio_id"] == p["id"]]
        lines.append(
            f"- Portfolio {p['name']} ({p.get('geography') or 'ALL'}) | default={bool(p.get('is_default'))} | stocks={len(p_stocks)}"
        )
        for s in p_stocks[:8]:
            ticker = s.get("ticker")
            sig = signals.get(ticker, {}).get("signal")
            fc = forecasts.get(ticker, {})
            direction = fc.get("direction")
            exp = fc.get("expected_change_pct")
            sent = sentiment.get(ticker, {}).get("sentiment_label")
            pe = fundamentals.get(ticker, {}).get("trailing_pe")
            lines.append(
                f"  - {ticker}: signal={sig or 'n/a'}, forecast_direction={direction or 'n/a'}, expected_change_pct={exp if exp is not None else 'n/a'}, sentiment={sent or 'n/a'}, pe_ratio={pe if pe is not None else 'n/a'}"
            )

    return "\n".join(lines)


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _keyword_score(query: str, stock_row: Dict[str, Any]) -> int:
    q = (query or "").lower()
    score = 0
    if not q:
        return score
    fields = [
        str(stock_row.get("ticker", "")).lower(),
        str(stock_row.get("company_name", "")).lower(),
        str(stock_row.get("sector", "")).lower(),
        str(stock_row.get("geography", "")).lower(),
        str(stock_row.get("portfolio_name", "")).lower(),
    ]
    for token in [t for t in q.replace("/", " ").split() if len(t) > 2]:
        if any(token in field for field in fields):
            score += 1
    return score


def _build_user_context_payload(user: Any, query: str) -> Dict[str, Any]:
    account_profile = {
        "username": getattr(user, "username", "") or "",
        "email": getattr(user, "email", "") or "",
        "is_authenticated": bool(getattr(user, "is_authenticated", False)),
    }

    portfolios = list(
        Portfolio.objects.filter(user=user)
        .values("id", "name", "geography", "is_default")
        .order_by("-is_default", "name")
    )
    if not portfolios:
        return {
            "account_profile": account_profile,
            "summary": {"portfolio_count": 0, "stock_count": 0},
            "portfolios": [],
            "stocks": [],
        }

    portfolio_map = {p["id"]: p for p in portfolios}
    portfolio_ids = list(portfolio_map.keys())

    stock_links = list(
        PortfolioStock.objects.filter(portfolio_id__in=portfolio_ids)
        .values("portfolio_id", "ticker", "company_name", "sector", "geography")
        .order_by("portfolio_id", "ticker")
    )
    tickers = sorted({row["ticker"] for row in stock_links if row.get("ticker")})

    forecasts = get_latest_forecasts_bulk(tickers) if tickers else {}
    signals = get_latest_signals_bulk(tickers) if tickers else {}
    sentiment = get_stocks_sentiment_bulk(tickers) if tickers else {}
    fundamentals = get_fundamentals_bulk(tickers) if tickers else {}
    latest_prices: Dict[str, Optional[float]] = {}
    for t in tickers:
        try:
            latest = get_latest_price(t) or {}
            latest_prices[t] = _to_float(latest.get("close"))
        except Exception:
            latest_prices[t] = None

    stock_rows: List[Dict[str, Any]] = []
    for row in stock_links:
        ticker = row.get("ticker")
        portfolio = portfolio_map.get(row["portfolio_id"], {})
        fc = forecasts.get(ticker, {})
        sg = signals.get(ticker, {})
        st = sentiment.get(ticker, {})
        fd = fundamentals.get(ticker, {})
        stock_rows.append(
            {
                "portfolio_name": portfolio.get("name"),
                "portfolio_geography": portfolio.get("geography"),
                "ticker": ticker,
                "company_name": row.get("company_name"),
                "sector": row.get("sector"),
                "geography": row.get("geography"),
                "current_price": latest_prices.get(ticker),
                "expected_change_pct": _to_float(fc.get("expected_change_pct")),
                "predicted_price": _to_float(fc.get("predicted_price")),
                "forecast_direction": fc.get("direction"),
                "forecast_confidence_r2": _to_float(fc.get("confidence_r2")),
                "signal": sg.get("signal"),
                "signal_confidence": _to_float(sg.get("confidence")),
                "sentiment_label": st.get("sentiment_label"),
                "sentiment_score": _to_float(st.get("sentiment_score")),
                "trailing_pe": _to_float(fd.get("trailing_pe")),
                "forward_pe": _to_float(fd.get("forward_pe")),
                "eps_trailing": _to_float(fd.get("eps_trailing")),
                "revenue_growth": _to_float(fd.get("revenue_growth")),
                "market_cap": _to_float(fd.get("market_cap")),
            }
        )

    ranking_like = any(k in (query or "").lower() for k in ("highest", "lowest", "top", "best", "worst"))

    # Query-aware relevance pruning to keep prompt compact but useful.
    # For ranking-like queries keep broad coverage to avoid missing the true extreme value.
    for row in stock_rows:
        row["_score"] = _keyword_score(query, row)
    ranked = sorted(
        stock_rows,
        key=lambda r: (
            r["_score"],
            _to_float(r.get("current_price")) or -999,
            _to_float(r.get("predicted_price")) or -999,
            _to_float(r.get("expected_change_pct")) or -999,
        ),
        reverse=True,
    )
    selected = ranked[:120] if ranking_like else ranked[:20]
    for row in selected:
        row.pop("_score", None)

    # Compact summaries
    by_portfolio: List[Dict[str, Any]] = []
    for p in portfolios:
        p_rows = [r for r in stock_rows if r.get("portfolio_name") == p.get("name")]
        by_portfolio.append(
            {
                "name": p.get("name"),
                "geography": p.get("geography"),
                "is_default": bool(p.get("is_default")),
                "stock_count": len(p_rows),
            }
        )

    return {
        "account_profile": account_profile,
        "summary": {
            "portfolio_count": len(portfolios),
            "stock_count": len(stock_rows),
            "selected_stock_context_count": len(selected),
        },
        "portfolios": by_portfolio,
        "stocks": selected,
    }


def _build_user_context_prompt(user: Any, query: str) -> str:
    payload = _build_user_context_payload(user, query)
    return json.dumps(payload, ensure_ascii=True)


def _resolve_metric_from_query(query: str) -> Optional[str]:
    q = (query or "").lower()
    if any(k in q for k in ("p/e", "pe ratio", "price to earnings", "trailing pe")):
        return "trailing_pe"
    if "market cap" in q:
        return "market_cap"
    if "eps" in q:
        return "eps_trailing"
    if any(k in q for k in ("predicted price", "forecast price", "prediction value")):
        return "predicted_price"
    if any(k in q for k in ("expected change", "change %", "change percentage", "expected return")):
        return "expected_change_pct"
    if any(k in q for k in ("price", "current price", "highest price", "lowest price")):
        return "current_price"
    return None


def _resolve_direction_from_query(query: str) -> Optional[str]:
    q = (query or "").lower()
    if any(k in q for k in ("highest", "top", "max", "best", "largest")):
        return "max"
    if any(k in q for k in ("lowest", "min", "worst", "smallest")):
        return "min"
    return None


def _answer_quant_query(user: Any, query: str) -> Optional[str]:
    metric = _resolve_metric_from_query(query)
    direction = _resolve_direction_from_query(query)
    if not metric or not direction:
        return None

    payload = _build_user_context_payload(user, query)
    rows = payload.get("stocks", [])
    if not rows:
        return "I could not find stock data in your portfolios yet."

    q = (query or "").lower()

    # Soft filters inferred from question
    if any(k in q for k in (" us ", " u.s", "american", "united states")) or q.startswith("us "):
        rows = [r for r in rows if str(r.get("geography", "")).upper() == "US" or str(r.get("portfolio_geography", "")).upper() == "US"]
    elif any(k in q for k in (" india", "indian")):
        rows = [r for r in rows if str(r.get("geography", "")).upper() == "IN" or str(r.get("portfolio_geography", "")).upper() == "IN"]

    if any(k in q for k in ("financial", "finance", "bank", "banking")):
        rows = [
            r
            for r in rows
            if any(k in str(r.get("sector", "")).lower() for k in ("financial", "finance", "bank"))
            or any(k in str(r.get("company_name", "")).lower() for k in ("financial", "finance", "bank"))
            or "financial" in str(r.get("portfolio_name", "")).lower()
        ]

    # Portfolio name targeting from phrase "... in <name> portfolio"
    marker = " portfolio"
    if marker in q and " in " in q:
        in_idx = q.rfind(" in ")
        if in_idx >= 0:
            fragment = q[in_idx + 4 : q.find(marker)].strip()
            if fragment:
                filtered = [r for r in rows if fragment in str(r.get("portfolio_name", "")).lower()]
                if filtered:
                    rows = filtered

    candidates = [r for r in rows if _to_float(r.get(metric)) is not None]
    if not candidates:
        metric_label = metric.replace("_", " ")
        return f"I found matching stocks but '{metric_label}' is not available in current data."

    key_fn = lambda r: _to_float(r.get(metric)) or float("-inf")
    best = max(candidates, key=key_fn) if direction == "max" else min(candidates, key=key_fn)
    value = _to_float(best.get(metric))
    if value is None:
        return None

    metric_label = {
        "current_price": "current price",
        "predicted_price": "predicted price",
        "trailing_pe": "trailing P/E",
        "expected_change_pct": "expected change %",
        "market_cap": "market cap",
        "eps_trailing": "trailing EPS",
    }.get(metric, metric.replace("_", " "))

    return (
        f"In your selected scope, {best.get('ticker')} ({best.get('company_name')}) has the "
        f"{'highest' if direction == 'max' else 'lowest'} {metric_label}: {value:.2f}. "
        f"Portfolio: {best.get('portfolio_name')}. Sector: {best.get('sector') or 'n/a'}."
    )


def _route_node(state: ChatState) -> ChatState:
    route = "auth" if state.get("is_authenticated") else "guest"
    return {"route": route}


def _load_user_context_node(state: ChatState) -> ChatState:
    user = state.get("user")
    if not user or isinstance(user, AnonymousUser):
        return {"user_context": ""}
    try:
        return {"user_context": _build_user_context_prompt(user, state.get("message", ""))}
    except Exception:
        return {"user_context": "User context is temporarily unavailable."}


def _respond_guest_node(state: ChatState) -> ChatState:
    system_prompt = (
        "You are AUTO INVEST assistant for public users. "
        "Give general, educational investing guidance. "
        "Do not claim access to private account data. "
        "Keep responses practical and concise. "
        "Not financial advice."
    )
    text = _call_chat_model(system_prompt, state.get("history", []), state.get("message", ""))
    return {"response": text}


def _respond_auth_node(state: ChatState) -> ChatState:
    user_context = state.get("user_context", "")
    system_prompt = (
        "You are AUTO INVEST personalized assistant for logged-in users. "
        "The USER_CONTEXT is authoritative account data. "
        "Answer using USER_CONTEXT first. "
        "Never say you don't have data if USER_CONTEXT includes relevant fields. "
        "If a metric is missing in USER_CONTEXT, say that clearly and suggest next available metric. "
        "Do not invent holdings, prices, or ratios. "
        "When user asks for best/highest/lowest/top, compute from USER_CONTEXT and show ticker + value + portfolio. "
        "Keep responses concise and practical. Not financial advice.\n\n"
        f"USER_CONTEXT_JSON:\n{user_context}"
    )
    text = _call_chat_model(system_prompt, state.get("history", []), state.get("message", ""))
    return {"response": text}


def _run_fallback(state: ChatState) -> str:
    if state.get("is_authenticated"):
        ctx = _build_user_context_prompt(state.get("user"), state.get("message", "")) if state.get("user") else ""
        prompt = (
            "You are AUTO INVEST personalized assistant. "
            "Use this context as authoritative account data. "
            "Compute rankings from it when asked.\n"
            f"{ctx}"
        )
    else:
        prompt = "You are AUTO INVEST public assistant. Give general investing guidance."
    return _call_chat_model(prompt, state.get("history", []), state.get("message", ""))


def generate_chat_response(*, user: Any, message: str, history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    normalized_history = _normalize_history(history or [])
    base_state: ChatState = {
        "message": message.strip(),
        "history": normalized_history,
        "is_authenticated": bool(getattr(user, "is_authenticated", False)),
        "user": user,
    }

    # General quantitative query handler (metric + ranking + optional filters)
    if base_state["is_authenticated"]:
        quantified = _answer_quant_query(user, base_state["message"])
        if quantified:
            return {"reply": quantified, "mode": "personalized"}

    if not LANGGRAPH_AVAILABLE:
        answer = _run_fallback(base_state)
        return {"reply": answer, "mode": "personalized" if base_state["is_authenticated"] else "generic"}

    graph = StateGraph(ChatState)
    graph.add_node("route", _route_node)
    graph.add_node("load_user_context", _load_user_context_node)
    graph.add_node("respond_guest", _respond_guest_node)
    graph.add_node("respond_auth", _respond_auth_node)
    graph.set_entry_point("route")
    graph.add_conditional_edges(
        "route",
        lambda st: st.get("route", "guest"),
        {"guest": "respond_guest", "auth": "load_user_context"},
    )
    graph.add_edge("load_user_context", "respond_auth")
    graph.add_edge("respond_guest", END)
    graph.add_edge("respond_auth", END)

    app = graph.compile()
    result = app.invoke(base_state)
    reply = str(result.get("response") or "").strip()
    if not reply:
        reply = "I could not generate a response right now. Please try again."

    return {"reply": reply, "mode": "personalized" if base_state["is_authenticated"] else "generic"}
