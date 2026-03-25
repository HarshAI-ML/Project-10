import os
from typing import Any, Dict, List, Optional, TypedDict

import requests
from django.contrib.auth.models import AnonymousUser

from analytics.data_access import (
    get_latest_forecasts_bulk,
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
            lines.append(
                f"  - {ticker}: signal={sig or 'n/a'}, forecast_direction={direction or 'n/a'}, expected_change_pct={exp if exp is not None else 'n/a'}, sentiment={sent or 'n/a'}"
            )

    return "\n".join(lines)


def _detect_top_performer_intent(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False
    portfolio_words = ("portfolio", "portfolios", "my stocks", "my holdings")
    top_words = (
        "best performing",
        "highest performing",
        "top performing",
        "best stock",
        "highest stock",
        "top stock",
        "which stock is best",
    )
    return any(p in text for p in portfolio_words) and any(t in text for t in top_words)


def _direct_top_performer_answer(user: Any) -> Optional[str]:
    portfolios = list(
        Portfolio.objects.filter(user=user).values("id", "name").order_by("-is_default", "name")
    )
    if not portfolios:
        return "You currently do not have any portfolios yet."

    portfolio_ids = [p["id"] for p in portfolios]
    stocks = list(
        PortfolioStock.objects.filter(portfolio_id__in=portfolio_ids).values("portfolio_id", "ticker")
    )
    tickers = sorted({s["ticker"] for s in stocks if s.get("ticker")})
    if not tickers:
        return "I could not find stocks in your portfolios yet."

    forecasts = get_latest_forecasts_bulk(tickers)
    ranked = []
    for ticker in tickers:
        fc = forecasts.get(ticker, {})
        change = fc.get("expected_change_pct")
        if change is None:
            continue
        ranked.append(
            {
                "ticker": ticker,
                "expected_change_pct": float(change),
                "predicted_price": fc.get("predicted_price"),
                "confidence_r2": fc.get("confidence_r2"),
            }
        )

    if not ranked:
        return (
            "I could not rank your portfolio stocks right now because forecast data is not available yet. "
            "Please run/refresh predictions and try again."
        )

    ranked.sort(key=lambda x: x["expected_change_pct"], reverse=True)
    best = ranked[0]
    name_map = {p["id"]: p["name"] for p in portfolios}
    containing = sorted({name_map[s["portfolio_id"]] for s in stocks if s.get("ticker") == best["ticker"]})
    portfolios_text = ", ".join(containing[:3])

    pct = round(best["expected_change_pct"], 2)
    conf = best.get("confidence_r2")
    conf_text = f"{round(float(conf), 2)}" if conf is not None else "n/a"
    return (
        f"Your current top forecasted performer is {best['ticker']} with expected change of {pct}% "
        f"(model confidence r2: {conf_text}). "
        f"It appears in: {portfolios_text}."
    )


def _route_node(state: ChatState) -> ChatState:
    route = "auth" if state.get("is_authenticated") else "guest"
    return {"route": route}


def _load_user_context_node(state: ChatState) -> ChatState:
    user = state.get("user")
    if not user or isinstance(user, AnonymousUser):
        return {"user_context": ""}
    try:
        return {"user_context": _build_user_context(user)}
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
        "Use the provided user context when relevant and be explicit about uncertainty. "
        "Never invent holdings. "
        "Prioritize actionable portfolio-aware explanations. "
        "Not financial advice.\n\n"
        f"USER_CONTEXT:\n{user_context}"
    )
    text = _call_chat_model(system_prompt, state.get("history", []), state.get("message", ""))
    return {"response": text}


def _run_fallback(state: ChatState) -> str:
    if state.get("is_authenticated"):
        ctx = _build_user_context(state.get("user")) if state.get("user") else ""
        prompt = (
            "You are AUTO INVEST personalized assistant. "
            "Use this context if useful:\n"
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

    if base_state["is_authenticated"] and _detect_top_performer_intent(base_state["message"]):
        direct = _direct_top_performer_answer(user)
        if direct:
            return {"reply": direct, "mode": "personalized"}

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
