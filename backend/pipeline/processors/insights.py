"""
Silver -> Gold: compute portfolio-facing insights from price history.
Writes GoldStockInsight records for each active ticker.
"""
import logging

from analytics.services.opportunity_engine import opportunity_engine
from pipeline.models import GoldStockInsight, SilverCleanedPrice
from portfolio.models import StockMaster

logger = logging.getLogger(__name__)


def _discount_level(current_price: float, average_price: float) -> str:
    ratio = current_price / max(average_price, 1.0)
    if ratio <= 0.9:
        return "HIGH"
    if ratio <= 1.0:
        return "MEDIUM"
    return "LOW"


def compute_insight_for_ticker(ticker: str) -> dict:
    rows = list(
        SilverCleanedPrice.objects
        .filter(ticker=ticker)
        .order_by("date")
        .values("date", "close")
    )
    if not rows:
        return {}

    prices = [float(row["close"]) for row in rows if row.get("close") is not None]
    dates = [row["date"].strftime("%Y-%m-%d") for row in rows if row.get("close") is not None]
    if not prices:
        return {}

    moving_avg = []
    for idx in range(len(prices)):
        start = max(0, idx - 4)
        window = prices[start:idx + 1]
        moving_avg.append(round(sum(window) / len(window), 2))

    current_price = prices[-1]
    average_price = sum(prices) / len(prices)
    pe_ratio = round(current_price / max(average_price, 1.0), 2)
    discount_level = _discount_level(current_price, average_price)
    score = opportunity_engine(pe_ratio=pe_ratio, discount_level=discount_level)

    return {
        "ticker": ticker,
        "date": rows[-1]["date"],
        "pe_ratio": pe_ratio,
        "discount_level": discount_level,
        "opportunity_score": score,
        "graph_data": {
            "dates": dates,
            "price": [round(value, 2) for value in prices],
            "moving_avg": moving_avg,
        },
    }


def compute_insights_all() -> dict:
    """
    Compute insights for all active tickers and write to GoldStockInsight.
    Returns summary dict.
    """
    tickers = list(
        StockMaster.objects.filter(is_active=True)
        .exclude(ticker__isnull=True)
        .exclude(ticker="")
        .values_list("ticker", flat=True)
    )

    logger.info(f"Computing insights for {len(tickers)} tickers")
    success = 0
    failed = 0

    for ticker in tickers:
        try:
            insight = compute_insight_for_ticker(ticker)
            if not insight:
                failed += 1
                continue

            GoldStockInsight.objects.update_or_create(
                ticker=ticker,
                date=insight["date"],
                defaults={
                    "pe_ratio": insight["pe_ratio"],
                    "discount_level": insight["discount_level"],
                    "opportunity_score": insight["opportunity_score"],
                    "graph_data": insight["graph_data"],
                },
            )
            success += 1
        except Exception as exc:
            failed += 1
            logger.error(f"[{ticker}] Insight computation failed: {exc}")

    logger.info(f"Insights done: {success} success, {failed} failed")
    return {"success": success, "failed": failed, "total": len(tickers)}
