"""
Silver sentiment processor.
Combines FinBERT (news) + price momentum + technical indicators.
Writes to SilverSentimentScore and GoldSectorSentiment.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Configurable text mode
# 'title' -> article title only (fast)
# 'both'  -> title + description (balanced)
TEXT_MODE = "both"

LABEL_WEIGHTS = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
BATCH_SIZE = 16
FINBERT_MODEL = "ProsusAI/finbert"

_finbert = None


def get_finbert():
    global _finbert
    if _finbert is None:
        from transformers import pipeline

        logger.info("Loading FinBERT model...")
        _finbert = pipeline(
            "text-classification",
            model=FINBERT_MODEL,
            top_k=None,
            device=-1,
        )
        logger.info("FinBERT loaded.")
    return _finbert


def weighted_sentiment(results: list) -> float:
    """Probability-weighted sentiment: positive=+1, neutral=0, negative=-1."""
    total = 0.0
    for result in results:
        label = str(result.get("label", "")).lower()
        total += LABEL_WEIGHTS.get(label, 0.0) * float(result.get("score", 0.0))
    return total


def normalize_to_10(weighted: float) -> float:
    """Map [-1, 1] to [0, 10]."""
    return round((weighted + 1.0) / 2.0 * 10.0, 4)


def get_text(article: dict, mode: str) -> str:
    title = str(article.get("title") or "").strip()
    desc = str(article.get("description") or "").strip()
    if mode == "title":
        return title
    combined = f"{title}. {desc}".strip(". ")
    return combined[:1000]


def score_articles_finbert(articles: list, mode: str = TEXT_MODE) -> float | None:
    """
    Run FinBERT on a list of article dicts.
    Returns normalized sentiment score [0, 10], or None if no usable articles.
    """
    if not articles:
        return None

    texts = [get_text(article, mode) for article in articles]
    texts = [text for text in texts if text and len(text) > 10]
    if not texts:
        return None

    finbert = get_finbert()
    texts = [" ".join(text.split()[:384]) for text in texts]

    all_weighted: list[float] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        results = finbert(batch, truncation=True, max_length=512)
        for result in results:
            all_weighted.append(weighted_sentiment(result))

    if not all_weighted:
        return None

    return normalize_to_10(float(np.mean(all_weighted)))


def score_price_momentum(ticker: str) -> float:
    """
    Compute price momentum score from recent returns in SilverCleanedPrice.
    Returns score in [0, 10]. Neutral fallback: 5.0.
    """
    from pipeline.models import SilverCleanedPrice

    rows = list(
        SilverCleanedPrice.objects
        .filter(ticker=ticker)
        .order_by("-date")
        .values("daily_return")[:20]
    )
    if not rows:
        return 5.0

    df = pd.DataFrame(rows)
    returns = df["daily_return"].dropna().tolist() if "daily_return" in df.columns else []
    returns = [float(value) for value in returns if np.isfinite(value)]
    if not returns:
        return 5.0

    ret_5 = float(np.mean(returns[:5])) if len(returns) >= 5 else float(np.mean(returns))
    ret_20 = float(np.mean(returns[:20])) if len(returns) >= 20 else float(np.mean(returns))
    momentum = (ret_5 * 0.7) + (ret_20 * 0.3)

    score = 5.0 + (momentum * 100.0)
    return float(np.clip(score, 0.0, 10.0))


def score_technicals(ticker: str) -> float:
    """
    Compute technical signal score from latest SilverCleanedPrice:
    RSI + price_vs_ma50 + MACD direction.
    Returns score in [0, 10]. Neutral fallback: 5.0.
    """
    from pipeline.models import SilverCleanedPrice

    row = (
        SilverCleanedPrice.objects
        .filter(ticker=ticker)
        .order_by("-date")
        .values("rsi_14", "price_vs_ma50", "macd", "macd_signal")
        .first()
    )
    if not row:
        return 5.0

    scores: list[float] = []

    rsi = row.get("rsi_14")
    if rsi is not None and np.isfinite(rsi):
        if rsi < 30:
            scores.append(7.5)
        elif rsi < 45:
            scores.append(6.0)
        elif rsi < 55:
            scores.append(5.0)
        elif rsi < 70:
            scores.append(4.0)
        else:
            scores.append(2.5)

    vs_ma50 = row.get("price_vs_ma50")
    if vs_ma50 is not None and np.isfinite(vs_ma50):
        scores.append(5.0 + float(np.clip(float(vs_ma50) * 0.5, -5.0, 5.0)))

    macd = row.get("macd")
    macd_sig = row.get("macd_signal")
    if macd is not None and macd_sig is not None and np.isfinite(macd) and np.isfinite(macd_sig):
        scores.append(7.0 if float(macd) > float(macd_sig) else 3.0)

    scores = [float(value) for value in scores if np.isfinite(value)]
    if not scores:
        return 5.0
    return float(np.clip(np.mean(scores), 0.0, 10.0))


def compute_sentiment_for_ticker(ticker: str, articles: list, text_mode: str = TEXT_MODE) -> dict:
    finbert_score = score_articles_finbert(articles, mode=text_mode)
    momentum_score = score_price_momentum(ticker)
    technical_score = score_technicals(ticker)
    if not np.isfinite(momentum_score):
        momentum_score = 5.0
    if not np.isfinite(technical_score):
        technical_score = 5.0
    if finbert_score is not None and not np.isfinite(finbert_score):
        finbert_score = None
    has_news = finbert_score is not None

    if has_news:
        final = (finbert_score * 0.5) + (momentum_score * 0.3) + (technical_score * 0.2)
        article_count = len(articles)
    else:
        final = (momentum_score * 0.6) + (technical_score * 0.4)
        finbert_score = None
        article_count = 0

    if not np.isfinite(final):
        final = 5.0
    final = float(np.clip(final, 0.0, 10.0))

    if final >= 6.5:
        label = "Positive"
    elif final >= 4.0:
        label = "Neutral"
    else:
        label = "Negative"

    return {
        "ticker": ticker,
        "date": date.today(),
        "sentiment_score": round(final, 4),
        "sentiment_label": label,
        "article_count": article_count,
        "finbert_score": round(finbert_score, 4) if finbert_score is not None else None,
        "momentum_score": round(momentum_score, 4),
        "technical_score": round(technical_score, 4),
        "model_used": "finbert+price" if has_news else "price_only",
        "text_mode": text_mode if has_news else "none",
    }


def build_news_index() -> dict[str, list[dict]]:
    """
    Build mapping: {ticker: [article dicts]} by matching tags/text to company keywords.
    """
    from pipeline.models import BronzeNewsArticle
    from portfolio.models import StockMaster

    articles = list(
        BronzeNewsArticle.objects
        .order_by("-ingested_at")
        .values("title", "description", "company_tags", "source_quality")[:2000]
    )
    stocks = list(StockMaster.objects.filter(is_active=True).values("ticker", "name"))

    keyword_map: dict[str, dict] = {}
    for stock in stocks:
        name = str(stock.get("name") or "")
        sanitized = (
            name.lower()
            .replace("ltd.", "")
            .replace("inc.", "")
            .replace("corp.", "")
            .replace("limited", "")
            .replace(",", " ")
        )
        words = sanitized.split()
        keywords = [word for word in words if len(word) > 3][:3]
        if keywords:
            keyword_map[stock["ticker"]] = {"keywords": keywords}

    ticker_articles = {stock["ticker"]: [] for stock in stocks}

    for article in articles:
        tags = str(article.get("company_tags") or "").lower()
        text = f"{article.get('title', '')} {article.get('description', '')}".lower()
        for ticker, meta in keyword_map.items():
            keywords = meta["keywords"]
            matched = any(keyword in tags for keyword in keywords) or any(keyword in text for keyword in keywords)
            if matched:
                ticker_articles[ticker].append(article)

    matched_count = sum(1 for article_rows in ticker_articles.values() if article_rows)
    logger.info("News index: %s articles matched to %s tickers", len(articles), matched_count)
    return ticker_articles


def compute_sentiment_all(text_mode: str = TEXT_MODE) -> dict:
    """
    Compute combined sentiment for all active tickers and write SilverSentimentScore.
    """
    from pipeline.models import SilverSentimentScore
    from portfolio.models import StockMaster

    tickers = list(
        StockMaster.objects
        .filter(is_active=True)
        .exclude(ticker__isnull=True)
        .exclude(ticker="")
        .values_list("ticker", flat=True)
    )
    logger.info("Computing sentiment for %s tickers (text_mode=%s)", len(tickers), text_mode)

    news_index = build_news_index()
    success = 0
    failed = 0
    no_news = 0
    rows = []

    for ticker in tickers:
        try:
            articles = news_index.get(ticker, [])
            if not articles:
                no_news += 1

            result = compute_sentiment_for_ticker(ticker, articles, text_mode=text_mode)
            rows.append(
                SilverSentimentScore(
                    ticker=result["ticker"],
                    date=result["date"],
                    sentiment_score=result["sentiment_score"],
                    sentiment_label=result["sentiment_label"],
                    article_count=result["article_count"],
                    finbert_score=result["finbert_score"],
                    momentum_score=result["momentum_score"],
                    technical_score=result["technical_score"],
                    model_used=result["model_used"],
                    text_mode=result["text_mode"],
                )
            )
            success += 1
        except Exception as exc:
            failed += 1
            logger.error("[%s] Sentiment failed: %s", ticker, exc)

    if rows:
        SilverSentimentScore.objects.filter(date=date.today()).delete()
        SilverSentimentScore.objects.bulk_create(rows, batch_size=100)

    logger.info("Sentiment done: %s ok / %s failed / %s no-news tickers", success, failed, no_news)
    return {"success": success, "failed": failed, "no_news": no_news, "total": len(tickers)}


def aggregate_sector_sentiment() -> dict:
    """
    Aggregate SilverSentimentScore per sector/geography into GoldSectorSentiment.
    """
    from pipeline.models import GoldSectorSentiment, SilverSentimentScore
    from portfolio.models import StockMaster

    today = date.today()
    silver_rows = list(
        SilverSentimentScore.objects
        .filter(date=today)
        .values("ticker", "sentiment_score")
    )
    if not silver_rows:
        logger.warning("No Silver sentiment for today - run compute_sentiment_all first")
        return {"sectors": 0}

    ticker_sector = {
        row["ticker"]: {"sector": row.get("sector") or "Unknown", "geography": row.get("geography") or ""}
        for row in StockMaster.objects.filter(is_active=True).values("ticker", "sector", "geography")
    }

    sector_scores: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in silver_rows:
        meta = ticker_sector.get(row["ticker"])
        if not meta:
            continue
        sector_scores[(meta["sector"], meta["geography"])].append(float(row["sentiment_score"]))

    GoldSectorSentiment.objects.filter(date=today).delete()
    gold_rows = []
    for (sector, geography), scores in sector_scores.items():
        valid_scores = [float(value) for value in scores if np.isfinite(value)]
        if not valid_scores:
            continue
        avg_score = float(np.mean(valid_scores))
        if avg_score >= 6.5:
            label = "Positive"
        elif avg_score >= 4.0:
            label = "Neutral"
        else:
            label = "Negative"

        gold_rows.append(
            GoldSectorSentiment(
                sector=sector,
                geography=geography,
                date=today,
                sentiment_score=round(avg_score, 4),
                sentiment_label=label,
                stock_count=len(scores),
            )
        )

    if gold_rows:
        GoldSectorSentiment.objects.bulk_create(gold_rows, batch_size=50)

    logger.info("Sector sentiment: %s sectors written to Gold", len(gold_rows))
    return {"sectors": len(gold_rows)}
