"""
Silver -> Gold: compute Buy/Sell/Hold signals from Silver indicators.
Rule-based - no ML needed, instant computation.
"""
import logging
from datetime import date

from pipeline.models import GoldStockSignal, SilverCleanedPrice
from portfolio.models import StockMaster

logger = logging.getLogger(__name__)


def compute_signal_for_ticker(ticker: str) -> dict:
    """
    Compute signal for a single ticker using latest Silver row.
    Rules:
        RSI  < 30  -> BUY  | RSI  > 70 -> SELL  | else -> HOLD
        MACD > signal line -> BUY | else -> SELL
        close > MA50 -> BUY | close < MA50 -> SELL | else -> HOLD
    Final: majority vote. Confidence = agreeing signals / 3
    """
    row = (
        SilverCleanedPrice.objects.filter(ticker=ticker)
        .order_by("-date")
        .values(
            "date",
            "close",
            "rsi_14",
            "macd",
            "macd_signal",
            "ma_50",
            "price_vs_ma20",
        )
        .first()
    )

    if not row:
        return {}

    rsi = row.get("rsi_14")
    macd = row.get("macd")
    macd_sig = row.get("macd_signal")
    close = row.get("close")
    ma50 = row.get("ma_50")

    if rsi is not None:
        if rsi < 30:
            rsi_signal = "BUY"
        elif rsi > 70:
            rsi_signal = "SELL"
        else:
            rsi_signal = "HOLD"
    else:
        rsi_signal = "NEUTRAL"

    if macd is not None and macd_sig is not None:
        macd_signal = "BUY" if macd > macd_sig else "SELL"
    else:
        macd_signal = "NEUTRAL"

    if close is not None and ma50 is not None:
        if close > ma50:
            ma_signal = "BUY"
        elif close < ma50:
            ma_signal = "SELL"
        else:
            ma_signal = "HOLD"
    else:
        ma_signal = "NEUTRAL"

    votes = [rsi_signal, macd_signal, ma_signal]
    valid_votes = [v for v in votes if v != "NEUTRAL"]

    if not valid_votes:
        final_signal = "NEUTRAL"
        confidence = 0.0
    else:
        buy_count = valid_votes.count("BUY")
        sell_count = valid_votes.count("SELL")
        hold_count = valid_votes.count("HOLD")

        if buy_count >= sell_count and buy_count >= hold_count:
            final_signal = "BUY"
            confidence = buy_count / len(valid_votes)
        elif sell_count >= buy_count and sell_count >= hold_count:
            final_signal = "SELL"
            confidence = sell_count / len(valid_votes)
        else:
            final_signal = "HOLD"
            confidence = hold_count / len(valid_votes)

    return {
        "ticker": ticker,
        "date": row["date"],
        "signal": final_signal,
        "confidence": round(confidence, 4),
        "rsi_signal": rsi_signal,
        "macd_signal": macd_signal,
        "ma_signal": ma_signal,
        "close": close,
        "rsi_14": rsi,
        "macd": macd,
        "macd_signal_line": macd_sig,
        "ma_50": ma50,
        "price_vs_ma20": row.get("price_vs_ma20"),
    }


def compute_signals_all() -> dict:
    """
    Compute signals for all active tickers and write to GoldStockSignal.
    Returns summary dict.
    """
    tickers = list(
        StockMaster.objects.filter(is_active=True)
        .exclude(ticker__isnull=True)
        .exclude(ticker="")
        .values_list("ticker", flat=True)
    )

    logger.info(f"Computing signals for {len(tickers)} tickers")
    success = 0
    failed = 0
    today = date.today()
    _ = today

    for ticker in tickers:
        try:
            result = compute_signal_for_ticker(ticker)
            if not result:
                failed += 1
                continue

            GoldStockSignal.objects.update_or_create(
                ticker=ticker,
                date=result["date"],
                defaults={
                    "signal": result["signal"],
                    "confidence": result["confidence"],
                    "rsi_signal": result["rsi_signal"],
                    "macd_signal": result["macd_signal"],
                    "ma_signal": result["ma_signal"],
                    "close": result["close"],
                    "rsi_14": result["rsi_14"],
                    "macd": result["macd"],
                    "macd_signal_line": result["macd_signal_line"],
                    "ma_50": result["ma_50"],
                    "price_vs_ma20": result["price_vs_ma20"],
                },
            )
            success += 1

        except Exception as e:
            failed += 1
            logger.error(f"[{ticker}] Signal computation failed: {e}")

    logger.info(f"Signals done: {success} success, {failed} failed")
    return {"success": success, "failed": failed, "total": len(tickers)}
