import math
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
try:
    from databricks import sql as databricks_sql
except ImportError:
    databricks_sql = None


# Databricks connectivity
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST", "")
DATABRICKS_HTTP_PATH = os.environ.get("DATABRICKS_HTTP_PATH", "")
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "")


def _databricks_available() -> bool:
    return bool(DATABRICKS_HOST and DATABRICKS_HTTP_PATH and DATABRICKS_TOKEN)


# Backward-compatible export used by reports.py and finbert.py
DATABRICKS_AVAILABLE = _databricks_available()


def _no_data_error(context: str) -> Dict[str, Any]:
    return {
        "error": f"{context} unavailable: Databricks is not configured or unreachable.",
        "source": "databricks",
        "status": "failed",
    }


def _safe_sql_string(value: str) -> str:
    return str(value).replace("'", "''")


def _slugify_company(name: str) -> str:
    text = str(name or "").strip().lower()
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _sentiment_color(score: float) -> str:
    if score >= 7:
        return "green"
    if score >= 4:
        return "yellow"
    return "red"


def clean_nan(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(i) for i in obj]
    return obj


def get_databricks_df(query: str) -> pd.DataFrame:
    if not _databricks_available():
        return pd.DataFrame()
    try:
        with databricks_sql.connect(
            server_hostname=DATABRICKS_HOST,
            http_path=DATABRICKS_HTTP_PATH,
            access_token=DATABRICKS_TOKEN,
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                cols = [desc[0] for desc in cursor.description]
                return pd.DataFrame(rows, columns=cols)
    except Exception as exc:
        print(f"Databricks query error: {exc}")
        return pd.DataFrame()


def get_sector_heatmap() -> Dict[str, Any]:
    if not _databricks_available():
        return _no_data_error("Heatmap")

    df = get_databricks_df(
        """
        SELECT company, signal, composite_score, rsi_14, price_vs_ma20, profitability_score
        FROM gold.investment_signals
        ORDER BY composite_score DESC
        """
    )
    if df.empty:
        return _no_data_error("Heatmap")

    companies = []
    for _, row in df.iterrows():
        score = float(row.get("composite_score", 5) or 5)
        companies.append(
            {
                "company": row.get("company"),
                "sentiment_score": round(score, 2),
                "signal": str(row.get("signal", "NEUTRAL")).upper(),
                "rsi_14": round(float(row.get("rsi_14", 50) or 50), 2),
                "price_vs_ma20_pct": round(float(row.get("price_vs_ma20", 0) or 0) * 100, 2),
                "profitability": round(float(row.get("profitability_score", 5) or 5), 2),
                "color": _sentiment_color(score),
            }
        )

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "source": "databricks",
        "companies": companies,
    }


def get_company_sentiment(company: str = None, granularity: str = "daily") -> Dict[str, Any]:
    if not _databricks_available():
        return _no_data_error("Sentiment")

    where = ""
    if company:
        company_safe = _safe_sql_string(company)
        where = f"WHERE LOWER(company) = LOWER('{company_safe}')"

    df = get_databricks_df(
        f"""
        SELECT
            company,
            signal_date AS score_date,
            signal,
            composite_score AS sentiment_score,
            momentum,
            rsi_14,
            price_vs_ma20,
            profitability_score,
            reasoning
        FROM gold.investment_signals
        {where}
        ORDER BY composite_score DESC
        """
    )
    if df.empty:
        return _no_data_error("Sentiment")

    return {
        "granularity": granularity,
        "source": "databricks",
        "count": len(df),
        "data": clean_nan(df.to_dict(orient="records")),
    }


def get_sector_insights() -> Dict[str, Any]:
    if not _databricks_available():
        return _no_data_error("Insights")

    signals_df = get_databricks_df(
        """
        SELECT company, signal, composite_score, rsi_14, price_vs_ma20, profitability_score
        FROM gold.investment_signals
        """
    )
    if signals_df.empty:
        return _no_data_error("Insights")

    sector_avg = round(float(signals_df["composite_score"].mean()), 2)
    sector_max = round(float(signals_df["composite_score"].max()), 2)
    sector_min = round(float(signals_df["composite_score"].min()), 2)

    if sector_avg >= 7:
        outlook, outlook_color = "BULLISH", "green"
    elif sector_avg >= 5.5:
        outlook, outlook_color = "CAUTIOUSLY POSITIVE", "yellow"
    elif sector_avg >= 4.5:
        outlook, outlook_color = "NEUTRAL", "yellow"
    else:
        outlook, outlook_color = "BEARISH", "red"

    signal_dist = (
        signals_df["signal"].astype(str).str.upper().value_counts().to_dict()
    )
    best_row = signals_df.loc[signals_df["composite_score"].idxmax()]
    worst_row = signals_df.loc[signals_df["composite_score"].idxmin()]

    news_df = get_databricks_df(
        """
        SELECT chunk_text, company_tags, source, published_at
        FROM silver.processed_news
        WHERE source = 'economic_times'
        ORDER BY published_at DESC
        LIMIT 3
        """
    )

    neg_events_df = get_databricks_df(
        """
        SELECT company, description AS subject, broadcast_date
        FROM bronze.raw_nse_announcements
        WHERE LOWER(description) RLIKE 'litigation|dispute|recall|penalty|loss|decline'
        ORDER BY broadcast_date DESC
        LIMIT 5
        """
    )

    return clean_nan(
        {
            "sector_avg_sentiment": sector_avg,
            "sector_max": sector_max,
            "sector_min": sector_min,
            "outlook": outlook,
            "outlook_color": outlook_color,
            "signal_distribution": signal_dist,
            "best_company": {
                "company": best_row.get("company"),
                "composite_score": round(float(best_row.get("composite_score", 0) or 0), 2),
                "signal": str(best_row.get("signal", "NEUTRAL")).upper(),
            },
            "worst_company": {
                "company": worst_row.get("company"),
                "composite_score": round(float(worst_row.get("composite_score", 0) or 0), 2),
                "signal": str(worst_row.get("signal", "NEUTRAL")).upper(),
            },
            "top_positive_news": news_df.fillna("").to_dict(orient="records") if not news_df.empty else [],
            "top_negative_events": neg_events_df.fillna("").to_dict(orient="records") if not neg_events_df.empty else [],
            "source": "databricks",
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
    )


def _classify_event(subject: str) -> str:
    text = str(subject or "").lower()
    if any(k in text for k in ["litigation", "dispute", "legal"]):
        return "LITIGATION"
    if any(k in text for k in ["investor meet", "analyst meet", "concall"]):
        return "INVESTOR_MEET"
    if any(k in text for k in ["quarterly result", "financial result", "earnings"]):
        return "EARNINGS"
    if any(k in text for k in ["electric", "ev launch", "electric vehicle"]):
        return "EV_LAUNCH"
    if any(k in text for k in ["capacity", "expansion", "new plant"]):
        return "PRODUCTION_EXPANSION"
    if "dividend" in text:
        return "DIVIDEND"
    return "GENERAL"


def get_events(company: str = None) -> Dict[str, Any]:
    if not _databricks_available():
        return _no_data_error("Events")

    where = ""
    if company:
        company_safe = _safe_sql_string(company)
        where = f"WHERE LOWER(company) LIKE LOWER('%{company_safe}%')"

    df = get_databricks_df(
        f"""
        SELECT company, description AS subject, broadcast_date, attachment_url
        FROM bronze.raw_nse_announcements
        {where}
        ORDER BY broadcast_date DESC
        LIMIT 50
        """
    )
    if df.empty:
        return {
            "company": company or "all",
            "count": 0,
            "events": [],
            "source": "databricks",
        }

    df["event_type"] = df["subject"].apply(_classify_event)
    df["event_date"] = pd.to_datetime(df["broadcast_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    events = df[["company", "event_date", "event_type", "subject", "attachment_url"]].fillna("").to_dict(orient="records")

    return {
        "company": company or "all",
        "count": len(events),
        "events": clean_nan(events),
        "source": "databricks",
    }


def get_latest_report() -> Dict[str, Any]:
    if not _databricks_available():
        return _no_data_error("Report")

    try:
        from .reports import generate_sector_report

        result = generate_sector_report()
        if result.get("error"):
            return _no_data_error("Report")
        return clean_nan(result)
    except Exception as exc:
        print(f"Report generation error: {exc}")
        return _no_data_error("Report")


def _build_company_report_via_groq(
    company_row: Dict[str, Any],
    fin_row: Dict[str, Any],
    events_df: pd.DataFrame,
    news_df: pd.DataFrame,
) -> Dict[str, str]:
    groq_api_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_api_key:
        return {
            "generated_by": "template-fallback",
            "report_text": (
                f"{company_row.get('company', 'Company')} currently has a "
                f"{company_row.get('signal', 'NEUTRAL')} signal with composite score "
                f"{company_row.get('composite_score', 'N/A')}. "
                "Databricks market, technical and fundamentals were used for this summary."
            ),
        }

    try:
        from groq import Groq

        model = "llama-3.1-8b-instant"
        client = Groq(api_key=groq_api_key)

        recent_events = []
        if not events_df.empty:
            for _, row in events_df.head(5).iterrows():
                recent_events.append(f"- {row.get('broadcast_date')}: {str(row.get('subject', ''))[:120]}")

        recent_news = []
        if not news_df.empty:
            for _, row in news_df.head(4).iterrows():
                recent_news.append(f"- {str(row.get('chunk_text', ''))[:140]}")

        prompt = f"""You are an equity research analyst.
Write a concise company intelligence report for {company_row.get('company')}.

Signal data:
- Signal: {company_row.get('signal')}
- Composite score: {company_row.get('composite_score')}
- Sentiment score: {company_row.get('sentiment_score')}
- RSI(14): {company_row.get('rsi_14')}
- Price vs MA20: {company_row.get('price_vs_ma20')}
- Profitability score: {company_row.get('profitability_score')}

Financials:
- Profit margin %: {fin_row.get('profit_margin_pct')}
- Revenue growth %: {fin_row.get('revenue_growth_pct')}
- Trailing PE: {fin_row.get('trailing_pe')}
- EPS trailing: {fin_row.get('eps_trailing')}
- Market cap cr: {fin_row.get('market_cap_cr')}
- Debt/Equity: {fin_row.get('debt_to_equity')}
- ROE %: {fin_row.get('roe_pct')}

Recent events:
{chr(10).join(recent_events) if recent_events else "- None"}

Recent news:
{chr(10).join(recent_news) if recent_news else "- None"}

Return 3 short paragraphs:
1) Current signal + technical stance
2) Fundamental quality and valuation
3) Risks and watchlist for next week
"""

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.25,
        )
        return {
            "generated_by": model,
            "report_text": response.choices[0].message.content.strip(),
        }
    except Exception as exc:
        print(f"Groq company report error: {exc}")
        return {
            "generated_by": "template-fallback",
            "report_text": (
                f"{company_row.get('company', 'Company')} has signal {company_row.get('signal', 'N/A')} "
                f"with composite score {company_row.get('composite_score', 'N/A')}. "
                "Groq generation failed, so this fallback summary is shown."
            ),
        }


def get_company_detail(slug: str) -> dict:
    """Load full company detail — built from Databricks Delta tables."""

    SLUG_TO_COMPANY = {
        "maruti-suzuki":     "Maruti Suzuki",
        "tata-motors":       "Tata Motors",
        "mahindra-mahindra": "Mahindra & Mahindra",
        "bajaj-auto":        "Bajaj Auto",
        "hero-motocorp":     "Hero MotoCorp",
    }

    SLUG_TO_TICKER = {
        "maruti-suzuki":     "MARUTI.NS",
        "tata-motors":       "TMPV.NS",
        "mahindra-mahindra": "M&M.NS",
        "bajaj-auto":        "BAJAJ-AUTO.NS",
        "hero-motocorp":     "HEROMOTOCO.NS",
    }

    company = SLUG_TO_COMPANY.get(slug)
    ticker  = SLUG_TO_TICKER.get(slug)

    if not company:
        return {"error": f"Company '{slug}' not found"}

    if not DATABRICKS_AVAILABLE:
        return {"error": "Databricks unavailable"}

    try:
        # Signal data
        signals_df = get_databricks_df(f"""
            SELECT company, signal, composite_score, momentum,
                   rsi_14, price_vs_ma20, profitability_score,
                   close, ma_20, price_momentum_5d, reasoning, signal_date
            FROM gold.investment_signals
            WHERE company = '{company}'
        """)

        # Financials
        fin_df = get_databricks_df(f"""
            SELECT company, profit_margin_pct, revenue_growth_pct,
                trailing_pe, eps_trailing, market_cap_cr,
                debt_to_equity, week52_high, week52_low
            FROM silver.processed_financials
            WHERE company = '{company}'
        """)

        # Stock history
        history_df = get_databricks_df(f"""
            SELECT date, open, high, low, close, volume,
                   daily_return, ma_5, ma_20, rsi_14, volatility_20d
            FROM silver.processed_stocks
            WHERE ticker = '{ticker}'
            ORDER BY date ASC
        """)

        # Recent events
        events_df = get_databricks_df(f"""
            SELECT description AS subject, broadcast_date, attachment_url
            FROM bronze.raw_nse_announcements
            WHERE company = '{company}'
            AND description IS NOT NULL
            AND description != ''
            ORDER BY broadcast_date DESC
            LIMIT 5
        """)

        # Transcript samples
        transcripts_df = get_databricks_df(f"""
            SELECT chunk_text, quarter, filing_date
            FROM silver.processed_transcripts
            WHERE company = '{company}'
            AND has_text = true
            LIMIT 3
        """)

        if signals_df.empty:
            return {"error": f"No signal data for {company}"}

        sig = signals_df.iloc[0]
        fin = fin_df.iloc[0] if not fin_df.empty else {}

        # Generate company report via Groq
        try:
            from .reports import generate_company_report
            report_text = generate_company_report(company, sig, fin, events_df)
        except Exception as e:
            report_text = f"Report generation failed: {e}"

        data = {
            "company":             company,
            "slug":                slug,
            "ticker":              ticker,
            "report_date":         datetime.now().strftime("%d %B %Y"),
            "generated_at":        datetime.now().isoformat(),
            "source":              "databricks",
            # Signal
            "signal":              sig.get("signal", "NEUTRAL"),
            "composite_score":     float(sig.get("composite_score", 5) or 5),
            "sentiment_score":     float(sig.get("composite_score", 5) or 5),
            "momentum":            float(sig.get("momentum", 0) or 0),
            "rsi_14":              float(sig.get("rsi_14", 50) or 50),
            "price_vs_ma20":       float(sig.get("price_vs_ma20", 0) or 0),
            "profitability_score": float(sig.get("profitability_score", 5) or 5),
            "price_momentum_5d":   float(sig.get("price_momentum_5d", 0) or 0),
            "close":               float(sig.get("close", 0) or 0),
            "ma_20":               float(sig.get("ma_20", 0) or 0),
            "reasoning":           sig.get("reasoning", ""),
            # Financials
            "profit_margin_pct":   _safe_float(fin.get("profit_margin_pct")),
            "revenue_growth_pct":  _safe_float(fin.get("revenue_growth_pct")),
            "trailing_pe":         _safe_float(fin.get("trailing_pe")),
            "eps_trailing":        _safe_float(fin.get("eps_trailing")),
            "market_cap_cr":       _safe_float(fin.get("market_cap_cr")),
            "debt_to_equity":      _safe_float(fin.get("debt_to_equity")),
            "roe_pct":             _safe_float(fin.get("roe_pct")),
            "week52_high":         _safe_float(fin.get("week52_high")),
            "week52_low":          _safe_float(fin.get("week52_low")),
            # Report
            "report_text":         report_text,
            "generated_by":        "llama-3.1-8b-instant",
            # Events
            "recent_events":       events_df.fillna("").to_dict(orient="records") if not events_df.empty else [],
            # Transcripts
            "transcript_samples":  transcripts_df.fillna("").to_dict(orient="records") if not transcripts_df.empty else [],
            # Stock history
            "stock_history":       history_df.fillna("").to_dict(orient="records") if not history_df.empty else [],
        }

        return clean_nan(data)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


def _safe_float(val):
    try:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return None
        return float(val)
    except:
        return None

def semantic_search(query: str, collection: str = "transcripts", company: str = None, n: int = 5) -> Dict[str, Any]:
    try:
        from .vector_store.search import search

        return {
            "query": query,
            "collection": collection,
            "results": search(query, collection=collection, company=company, n_results=n),
            "source": "vector_store",
        }
    except Exception as exc:
        return {
            "error": f"Semantic search unavailable: {exc}",
            "source": "vector_store",
            "status": "failed",
        }
