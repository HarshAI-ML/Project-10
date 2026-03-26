import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, TypedDict
import json

import requests
from django.contrib.auth.models import AnonymousUser
from django.db import connection

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


VECTOR_DOC_TYPES = {"news", "stock_insight", "stock_sentiment", "sector_sentiment"}
VECTOR_TOP_K = int(os.getenv("CHATBOT_VECTOR_TOP_K", "5"))
VECTOR_SNIPPET_CHARS = int(os.getenv("CHATBOT_VECTOR_SNIPPET_CHARS", "260"))
EMBEDDING_MODEL_NAME = os.getenv("CHATBOT_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

GENERIC_SUGGESTED_QUESTIONS = [
    "What is a simple way to start investing?",
    "How do I reduce risk in a stock portfolio?",
    "What is the difference between price and value?",
    "Which sectors usually look safer in uncertain markets?",
    "How do I read a buy, hold, or sell signal?",
    "What should I check before buying a stock?",
]

PERSONALIZED_SUGGESTED_QUESTIONS = [
    "Which stock in my portfolio has the highest expected upside?",
    "Which holding has the best buy signal right now?",
    "Which stock has the lowest P/E ratio in my portfolio?",
    "What are the riskiest holdings in my current portfolio?",
    "Show me the strongest stock by sentiment in my portfolio.",
    "What is my portfolio missing for better balance?",
]


class ChatState(TypedDict, total=False):
    message: str
    history: List[Dict[str, str]]
    is_authenticated: bool
    user: Any
    route: str
    user_context: str
    vector_context: str
    user_context_payload: Dict[str, Any]
    response: str


def _normalize_history(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Normalize chat history to ensure consistent format.

    Takes raw history items and returns a cleaned list containing only
    user and assistant messages with content truncated to 1000 characters.
    Limits history to last 10 messages to prevent excessive context.

    Args:
        history: Raw chat history list of dictionaries with 'role' and 'content' keys

    Returns:
        List of normalized dictionaries with 'role' and 'content' strings
    """
    cleaned: List[Dict[str, str]] = []
    for item in (history or [])[-10:]:
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            cleaned.append({"role": role, "content": content[:1000]})
    return cleaned


@lru_cache(maxsize=1)
def _get_embedding_model():
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        return None

    try:
        return SentenceTransformer(EMBEDDING_MODEL_NAME)
    except Exception:
        return None


def _to_vector_literal(values: List[float]) -> str:
    return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"


def _truncate_text(value: Any, limit: int = VECTOR_SNIPPET_CHARS) -> str:
    text = str(value or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def _safe_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _portfolio_tickers_from_payload(payload: Dict[str, Any]) -> List[str]:
    stocks = payload.get("stocks", []) if isinstance(payload, dict) else []
    tickers = [str(row.get("ticker", "")).strip() for row in stocks if row.get("ticker")]
    return list(dict.fromkeys([ticker for ticker in tickers if ticker]))


def _vector_search_documents(
    query: str,
    *,
    tickers: Optional[List[str]] = None,
    doc_types: Optional[List[str]] = None,
    top_k: int = VECTOR_TOP_K,
) -> List[Dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []

    if connection.vendor != "postgresql":
        return []

    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.ai_vector_documents');")
        if cursor.fetchone()[0] is None:
            return []

    doc_types = [doc_type for doc_type in (doc_types or []) if doc_type in VECTOR_DOC_TYPES]
    tickers = [ticker for ticker in (tickers or []) if ticker]

    emb_model = _get_embedding_model()
    embedding = None
    if emb_model is not None:
        try:
            embedding = emb_model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0].tolist()
        except Exception:
            embedding = None

    snippet_limit = VECTOR_SNIPPET_CHARS
    select_columns = """
        doc_type, source_table, source_pk, ticker, sector, geography, as_of_date,
        LEFT(content, %s) AS snippet, metadata
    """

    if embedding is not None:
        sql = f"""
            SELECT {select_columns},
                   (embedding <=> %s::vector) AS distance
            FROM ai_vector_documents
            WHERE embedding IS NOT NULL
        """
        params: List[Any] = [snippet_limit, _to_vector_literal(embedding)]
        if doc_types:
            sql += " AND doc_type = ANY(%s)"
            params.append(doc_types)
        if tickers:
            sql += " AND ticker = ANY(%s)"
            params.append(tickers)
        sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params.extend([_to_vector_literal(embedding), top_k])
    else:
        sql = f"""
            SELECT {select_columns},
                   NULL AS distance
            FROM ai_vector_documents
            WHERE 1 = 1
        """
        params = [snippet_limit]
        pattern = f"%{query}%"
        sql += " AND (content ILIKE %s OR source_table ILIKE %s OR ticker ILIKE %s)"
        params.extend([pattern, pattern, pattern])
        if doc_types:
            sql += " AND doc_type = ANY(%s)"
            params.append(doc_types)
        if tickers:
            sql += " AND ticker = ANY(%s)"
            params.append(tickers)
        sql += " ORDER BY updated_at DESC LIMIT %s"
        params.append(top_k)

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    docs: List[Dict[str, Any]] = []
    for row in rows:
        docs.append(
            {
                "doc_type": row[0],
                "source_table": row[1],
                "source_pk": row[2],
                "ticker": row[3],
                "sector": row[4],
                "geography": row[5],
                "as_of_date": row[6],
                "snippet": row[7],
                "metadata": _safe_json_dict(row[8]),
                "distance": row[9],
            }
        )
    return docs


def _build_vector_context(query: str, user_context_payload: Optional[Dict[str, Any]] = None) -> str:
    tickers = _portfolio_tickers_from_payload(user_context_payload or {})
    docs = _vector_search_documents(
        query,
        tickers=tickers[:25] if tickers else None,
        doc_types=sorted(VECTOR_DOC_TYPES),
        top_k=VECTOR_TOP_K,
    )
    if not docs:
        return ""

    lines = ["VECTOR_CONTEXT:"]
    for doc in docs:
        heading_bits = [doc.get("doc_type") or "document"]
        if doc.get("ticker"):
            heading_bits.append(str(doc["ticker"]))
        if doc.get("sector"):
            heading_bits.append(str(doc["sector"]))
        if doc.get("geography"):
            heading_bits.append(str(doc["geography"]))
        if doc.get("as_of_date"):
            heading_bits.append(str(doc["as_of_date"]))
        heading = " | ".join(heading_bits)
        lines.append(f"- {heading}: {_truncate_text(doc.get('snippet') or '', VECTOR_SNIPPET_CHARS)}")
    return "\n".join(lines)


def _suggested_questions(is_authenticated: bool) -> List[str]:
    return PERSONALIZED_SUGGESTED_QUESTIONS if is_authenticated else GENERIC_SUGGESTED_QUESTIONS


def _call_groq_chat(system_prompt: str, history: List[Dict[str, str]], user_message: str) -> str:
    """
    Generate a chat response using the Groq API.

    Sends a request to Groq's chat completion endpoint with the provided
    system prompt, conversation history, and user message.

    Args:
        system_prompt: Instructions for the model's behavior
        history: List of previous conversation messages (role/content dicts)
        user_message: The current user input to respond to

    Returns:
        Generated response text from the model, or an error message if
        the API call fails or is not configured
    """
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
    """
    Generate a chat response using the OpenRouter API.

    Sends a request to OpenRouter's chat completion endpoint with the provided
    system prompt, conversation history, and user message.

    Args:
        system_prompt: Instructions for the model's behavior
        history: List of previous conversation messages (role/content dicts)
        user_message: The current user input to respond to

    Returns:
        Generated response text from the model, or an error message if
        the API call fails or is not configured
    """
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
    Select and call the appropriate chat model provider based on configuration.

    Provider selection logic:
    - CHAT_PROVIDER=openrouter => Use OpenRouter only
    - CHAT_PROVIDER=groq       => Use Groq only
    - default/auto             => Try Groq first, fallback to OpenRouter on failure

    Args:
        system_prompt: Instructions for the model's behavior
        history: List of previous conversation messages (role/content dicts)
        user_message: The current user input to respond to

    Returns:
        Generated response text from the selected model provider
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
    """
    Build a text summary of the user's portfolio for use in LLM prompts.

    Fetches the user's portfolios and stocks, then creates a formatted text
    summary including portfolio names, stock tickers, signals, forecasts,
    sentiment, and fundamentals data.

    Args:
        user: Django user object (authenticated)

    Returns:
        Formatted string containing portfolio summary, or message if user has no portfolios
    """
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
    """
    Safely convert a value to float, returning None if conversion fails.

    Args:
        value: Any value to convert to float

    Returns:
        Float value if conversion succeeds, None otherwise
    """
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _keyword_score(query: str, stock_row: Dict[str, Any]) -> int:
    """
    Calculate a relevance score for a stock row based on keyword matching.

    Scores how well a stock matches a query by checking if query tokens
    appear in various stock fields (ticker, company name, sector, etc.).

    Args:
        query: User's search query string
        stock_row: Dictionary containing stock data with ticker, company_name, etc.

    Returns:
        Integer score representing number of query tokens found in stock fields
    """
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
    """
    Build a structured payload containing the user's portfolio data for LLM context.

    Creates a comprehensive JSON-serializable dictionary containing:
    - Account profile information (username, email, auth status)
    - Portfolio summary (counts, default/custom status)
    - Detailed stock data with current prices, forecasts, signals, sentiment, and fundamentals
    - Query-aware pruning to keep payload size manageable while preserving relevance

    Args:
        user: Django user object (authenticated)
        query: Current user query used for relevance-based pruning

    Returns:
        Dictionary containing account profile, summary statistics, portfolios, and stocks data
    """
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
    stocks_by_portfolio: Dict[Any, List[Dict[str, Any]]] = {}
    for row in stock_links:
        stocks_by_portfolio.setdefault(row["portfolio_id"], []).append(row)
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
        p_rows = stocks_by_portfolio.get(p["id"], [])
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
    """
    Convert user context payload to a JSON string for inclusion in LLM prompts.

    Args:
        user: Django user object (authenticated)
        query: Current user query used for relevance-based pruning

    Returns:
        JSON string representation of the user's portfolio context
    """
    payload = _build_user_context_payload(user, query)
    return json.dumps(payload, ensure_ascii=True)


def _resolve_metric_from_query(query: str) -> Optional[str]:
    """
    Determine which financial metric a query is asking about.

    Maps common phrasing in user questions to internal metric field names.

    Args:
        query: User's question string

    Returns:
        String metric name (e.g., "trailing_pe", "current_price") or None if no match
    """
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
    """
    Determine if a query is asking for a maximum or minimum value.

    Looks for keywords indicating whether the user wants the highest/best
    or lowest/worst value of a metric.

    Args:
        query: User's question string

    Returns:
        "max" for highest/best, "min" for lowest/worst, or None if unclear
    """
    q = (query or "").lower()
    if any(k in q for k in ("highest", "top", "max", "best", "largest")):
        return "max"
    if any(k in q for k in ("lowest", "min", "worst", "smallest")):
        return "min"
    return None


def _answer_quant_query(user: Any, query: str, payload: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Attempt to answer a quantitative question directly from portfolio data.

    Parses questions asking for highest/lowest values of financial metrics
    (like PE ratio, price, predicted price, etc.) and answers them by
    scanning the user's portfolio data. Applies filters for geography,
    sector, and portfolio name based on keywords in the question.

    Args:
        user: Django user object (authenticated)
        query: User's question string

    Returns:
        Formatted answer string if the question can be answered from portfolio data,
        None if the question is not quantitative or cannot be answered
    """
    metric = _resolve_metric_from_query(query)
    direction = _resolve_direction_from_query(query)
    if not metric or not direction:
        return None

    payload = payload or _build_user_context_payload(user, query)
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
    """
    Route the conversation to either authenticated or guest flow.

    Determines whether to use the personalized (auth) or generic (guest)
    chatbot response based on user authentication status.

    Args:
        state: Current chat state containing user authentication info

    Returns:
        Dictionary with 'route' key set to 'auth' or 'guest'
    """
    route = "auth" if state.get("is_authenticated") else "guest"
    return {"route": route}


def _load_user_context_node(state: ChatState) -> ChatState:
    """
    Load the user's portfolio context for inclusion in the LLM prompt.

    For authenticated users, builds a JSON payload containing portfolio
    and stock data. For guests or anonymous users, returns empty context.

    Args:
        state: Current chat state containing user and message

    Returns:
        Dictionary with 'user_context' key containing JSON string or
        empty string/unavailable message
    """
    user = state.get("user")
    if not user or isinstance(user, AnonymousUser):
        return {"user_context": "", "vector_context": ""}
    if state.get("user_context") and state.get("vector_context") is not None:
        return {}
    try:
        payload = state.get("user_context_payload") or _build_user_context_payload(user, state.get("message", ""))
        return {
            "user_context": json.dumps(payload, ensure_ascii=True),
            "vector_context": _build_vector_context(state.get("message", ""), payload),
            "user_context_payload": payload,
        }
    except Exception:
        return {"user_context": "User context is temporarily unavailable.", "vector_context": ""}


def _respond_guest_node(state: ChatState) -> ChatState:
    """
    Generate a response for guest/unauthenticated users.

    Uses a generic system prompt that provides educational investing guidance
    without access to private account data.

    Args:
        state: Current chat state containing message and history

    Returns:
        Dictionary with 'response' key containing the generated text
    """
    system_prompt = (
        "You are AUTO INVEST assistant for public users. "
        "Give general, educational investing guidance. "
        "Do not claim access to private account data. "
        "Keep responses practical and concise. "
        "Not financial advice."
    )
    vector_context = state.get("vector_context", "")
    if vector_context:
        system_prompt = f"{system_prompt}\n\n{vector_context}"
    text = _call_chat_model(system_prompt, state.get("history", []), state.get("message", ""))
    return {"response": text}


def _respond_auth_node(state: ChatState) -> ChatState:
    """
    Generate a personalized response for authenticated users.

    Uses the user's portfolio context (from USER_CONTEXT) to provide
    personalized investment guidance. The system prompt instructs the model
    to prioritize context data and avoid inventing information.

    Args:
        state: Current chat state containing user_context, message, and history

    Returns:
        Dictionary with 'response' key containing the generated text
    """
    user_context = state.get("user_context", "")
    vector_context = state.get("vector_context", "")
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
    if vector_context:
        system_prompt = f"{system_prompt}\n\n{vector_context}"
    text = _call_chat_model(system_prompt, state.get("history", []), state.get("message", ""))
    return {"response": text}


def _run_fallback(state: ChatState) -> str:
    """
    Generate a fallback response when LangGraph is not available.

    Constructs a prompt based on user authentication status and calls the
    chat model directly, bypassing the LangGraph workflow.

    Args:
        state: Current chat state containing user, message, and history

    Returns:
        Generated response text from the chat model
    """
    if state.get("is_authenticated"):
        ctx = state.get("user_context", "")
        vector_ctx = state.get("vector_context", "")
        prompt = (
            "You are AUTO INVEST personalized assistant. "
            "Use this context as authoritative account data. "
            "Compute rankings from it when asked.\n"
        )
        if ctx:
            prompt = f"{prompt}{ctx}"
        if vector_ctx:
            prompt = f"{prompt}\n\n{vector_ctx}"
    else:
        prompt = "You are AUTO INVEST public assistant. Give general investing guidance."
        vector_ctx = state.get("vector_context", "")
        if vector_ctx:
            prompt = f"{prompt}\n\n{vector_ctx}"
    return _call_chat_model(prompt, state.get("history", []), state.get("message", ""))


def generate_chat_response(*, user: Any, message: str, history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Generate a chatbot response for a user, either generic or personalized.

    This is the main entry point for the chatbot service. It handles:
    - Normalizing chat history
    - Checking for quantitative questions that can be answered directly from portfolio data
    - Routing to appropriate flow (generic vs personalized) based on auth status
    - Using LangGraph workflow when available for structured processing
    - Falling back to direct LLM calls when LangGraph is not available

    Args:
        user: Django user object (can be AnonymousUser for guests)
        message: The user's input message
        history: Optional list of previous conversation messages (default: None)

    Returns:
        Dictionary with:
        - reply: The generated response text
        - mode: Either "personalized" (for auth users) or "generic" (for guests)
    """
    normalized_history = _normalize_history(history or [])
    user_context_payload = None
    user_context = ""
    vector_context = ""
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    if is_authenticated:
        try:
            user_context_payload = _build_user_context_payload(user, message.strip())
            user_context = json.dumps(user_context_payload, ensure_ascii=True)
        except Exception:
            user_context_payload = None
            user_context = ""
    try:
        vector_context = _build_vector_context(message.strip(), user_context_payload)
    except Exception:
        vector_context = ""

    base_state: ChatState = {
        "message": message.strip(),
        "history": normalized_history,
        "is_authenticated": is_authenticated,
        "user": user,
        "user_context_payload": user_context_payload or {},
        "user_context": user_context,
        "vector_context": vector_context,
    }

    # General quantitative query handler (metric + ranking + optional filters)
    if base_state["is_authenticated"]:
        quantified = _answer_quant_query(user, base_state["message"], payload=user_context_payload)
        if quantified:
            return {
                "reply": quantified,
                "mode": "personalized",
                "suggestions": _suggested_questions(True),
            }

    if not LANGGRAPH_AVAILABLE:
        answer = _run_fallback(base_state)
        is_authenticated = base_state["is_authenticated"]
        return {
            "reply": answer,
            "mode": "personalized" if is_authenticated else "generic",
            "suggestions": _suggested_questions(is_authenticated),
        }

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

    is_authenticated = bool(base_state["is_authenticated"])
    return {
        "reply": reply,
        "mode": "personalized" if is_authenticated else "generic",
        "suggestions": _suggested_questions(is_authenticated),
    }
