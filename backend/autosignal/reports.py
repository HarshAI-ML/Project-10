import os
import math
import pandas as pd
from datetime import datetime
from groq import Groq
from .services import get_databricks_df, DATABRICKS_AVAILABLE

GROQ_MODEL  = "llama-3.1-8b-instant"

def get_groq_client():
    return Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

def generate_sector_report() -> dict:
    """Generate Groq sector report using Databricks data."""
    if not DATABRICKS_AVAILABLE:
        return {"error": "Databricks not configured"}

    # Load signals
    signals_df = get_databricks_df("""
        SELECT company, signal, composite_score, rsi_14,
               price_vs_ma20, profitability_score, close,
               price_momentum_5d, reasoning
        FROM gold.investment_signals
        ORDER BY composite_score DESC
    """)

    # Load financials
    fin_df = get_databricks_df("""
        SELECT company, profit_margin_pct, revenue_growth_pct,
               trailing_pe, eps_trailing, market_cap_cr, debt_to_equity,
               week52_high, week52_low
        FROM silver.processed_financials
    """)

    # Load sentiment if available
    try:
        sent_df = get_databricks_df("""
            SELECT company, sentiment_score, article_count,
                   transcript_count, sentiment_intensity, momentum
            FROM gold.company_sentiment_scores
            ORDER BY score_date DESC
            LIMIT 5
        """)
    except:
        sent_df = pd.DataFrame()

    # Load recent events
    events_df = get_databricks_df("""
        SELECT company, description AS subject, broadcast_date
        FROM bronze.raw_nse_announcements
        WHERE broadcast_date >= date_sub(current_date(), 7)
        AND description IS NOT NULL AND description != ''
        ORDER BY broadcast_date DESC
        LIMIT 10
    """)

    # Load top news samples
    news_df = get_databricks_df("""
        SELECT company_tags, chunk_text
        FROM silver.processed_news
        WHERE company_tags != 'sector'
        AND source = 'economic_times'
        LIMIT 5
    """)

    # Merge signals + financials
    if not signals_df.empty and not fin_df.empty:
        merged = signals_df.merge(fin_df, on="company", how="left")
        if not sent_df.empty:
            merged = merged.merge(
                sent_df[["company", "sentiment_score", "article_count", "momentum"]],
                on="company", how="left"
            )
    else:
        return {"error": "No signals data in Databricks"}

    # Build company block
    company_lines = []
    for _, row in merged.iterrows():
        def sf(col, fmt=".2f", suffix=""):
            val = row.get(col)
            try:
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    return "N/A"
                return f"{float(val):{fmt}}{suffix}"
            except:
                return "N/A"

        company_lines.append(f"""
  {row['company']}:
    Signal:          {row.get('signal', 'N/A')}
    Composite Score: {sf('composite_score')}/10
    Sentiment Score: {sf('sentiment_score')}/10
    Current Price:   Rs. {sf('close')}
    RSI (14-day):    {sf('rsi_14')}
    Price vs MA20:   {sf('price_vs_ma20', '.1%')}
    5-day Momentum:  {sf('price_momentum_5d', '.2%')}
    Profit Margin:   {sf('profit_margin_pct', '.1f', '%')}
    Revenue Growth:  {sf('revenue_growth_pct', '.1f', '%')}
    Trailing PE:     {sf('trailing_pe', '.1f', 'x')}
    Market Cap:      Rs. {sf('market_cap_cr', '.0f')} Cr
    Debt/Equity:     {sf('debt_to_equity', '.2f')}""")

    company_block = "\n".join(company_lines)

    # Build events block
    if not events_df.empty:
        event_lines = [
            f"  - {row['company']}: {str(row['subject'])[:100]}"
            for _, row in events_df.head(5).iterrows()
        ]
        events_block = "\n".join(event_lines)
    else:
        events_block = "  No recent events"

    # Build news block
    if not news_df.empty:
        news_lines = [
            f"  - {row['company_tags']}: {str(row['chunk_text'])[:100]}"
            for _, row in news_df.head(3).iterrows()
        ]
        news_block = "\n".join(news_lines)
    else:
        news_block = "  No recent news"

    # Signal distribution
    buy_count     = len(merged[merged["signal"] == "BUY"])
    neutral_count = len(merged[merged["signal"] == "NEUTRAL"])
    risk_count    = len(merged[merged["signal"] == "RISK_ALERT"])
    sector_avg    = round(float(merged["composite_score"].mean()), 2)
    top_row       = merged.loc[merged["composite_score"].idxmax()]
    bottom_row    = merged.loc[merged["composite_score"].idxmin()]

    prompt = f"""You are a senior equity analyst at a top Indian brokerage covering the automobile sector.

Today is {datetime.now().strftime('%d %B %Y')}. Complete intelligence data for Indian Auto Sector:

SECTOR OVERVIEW:
- Sector average composite score: {sector_avg}/10
- Signal distribution: {buy_count} BUY | {neutral_count} NEUTRAL | {risk_count} RISK ALERT
- Top performer: {top_row['company']} ({top_row['composite_score']:.2f}/10) — {top_row['signal']}
- Weakest: {bottom_row['company']} ({bottom_row['composite_score']:.2f}/10) — {bottom_row['signal']}

COMPANY DATA:
{company_block}

RECENT CORPORATE EVENTS (last 7 days):
{events_block}

RECENT NEWS:
{news_block}

Write a professional 4-paragraph sector intelligence report:

Paragraph 1 - SECTOR PULSE: Analyze composite scores and RSI levels.
Paragraph 2 - STANDOUT COMPANIES: Compare top vs worst with specific numbers.
Paragraph 3 - INVESTMENT RECOMMENDATIONS: For each company: ACCUMULATE / HOLD / AVOID with one-line reason.
Paragraph 4 - RISKS AND OUTLOOK: Top 3 risks, key catalyst to watch.

Rules:
- Cite specific numbers (scores, RSI, price vs MA20, margins)
- Recommendations must be data-driven
- Tone: institutional, analytical, direct
- Maximum 450 words
- No disclaimers"""

    client      = get_groq_client()
    response    = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.3,
    )
    report_text = response.choices[0].message.content.strip()

    return {
        "report_date":          datetime.now().strftime("%d %B %Y"),
        "generated_at":         datetime.now().isoformat(),
        "sector_avg_sentiment": sector_avg,
        "top_company":          top_row["company"],
        "top_score":            round(float(top_row["composite_score"]), 2),
        "bottom_company":       bottom_row["company"],
        "bottom_score":         round(float(bottom_row["composite_score"]), 2),
        "signal_distribution":  {"BUY": buy_count, "NEUTRAL": neutral_count, "RISK_ALERT": risk_count},
        "report_text":          report_text,
        "generated_by":         GROQ_MODEL,
        "source":               "databricks",
        "companies":            merged[["company", "signal", "composite_score", "reasoning"]].to_dict(orient="records"),
    }
    
    
def generate_company_report(company: str, sig, fin, events_df) -> str:
    """Generate a company-specific report using Groq."""
    try:
        def sf(val, fmt=".2f", suffix=""):
            try:
                if val is None or (isinstance(val, float) and math.isnan(float(val))):
                    return "N/A"
                return f"{float(val):{fmt}}{suffix}"
            except:
                return "N/A"

        events_text = ""
        if not events_df.empty:
            events_text = "\n".join([
                f"- {str(row.get('subject',''))[:100]}"
                for _, row in events_df.head(3).iterrows()
            ])
        else:
            events_text = "No recent events"

        prompt = f"""You are a senior equity analyst covering Indian automobile stocks.

Analyze {company} based on this data:

SIGNAL: {sig.get('signal', 'N/A')}
COMPOSITE SCORE: {sf(sig.get('composite_score'))}/10
CURRENT PRICE: Rs. {sf(sig.get('close'))}
RSI (14-day): {sf(sig.get('rsi_14'))}
PRICE vs MA20: {sf(sig.get('price_vs_ma20'), '.1%')}
5-DAY MOMENTUM: {sf(sig.get('price_momentum_5d'), '.2%')}
PROFIT MARGIN: {sf(fin.get('profit_margin_pct'), '.1f', '%')}
REVENUE GROWTH: {sf(fin.get('revenue_growth_pct'), '.1f', '%')}
TRAILING PE: {sf(fin.get('trailing_pe'), '.1f', 'x')}
MARKET CAP: Rs. {sf(fin.get('market_cap_cr'), '.0f')} Cr
DEBT/EQUITY: {sf(fin.get('debt_to_equity'))}

RECENT CORPORATE EVENTS:
{events_text}

Write a 3-paragraph company intelligence report:
1. Current sentiment and what is driving it
2. Financial health and stock performance assessment  
3. Investment outlook: clearly state ACCUMULATE / HOLD / AVOID with specific reasons

Rules:
- Cite specific numbers from the data
- Objective and data-driven tone
- Maximum 250 words
- No disclaimers"""

        client   = get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Report generation failed: {e}"
