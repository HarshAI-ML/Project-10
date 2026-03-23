from __future__ import annotations

def plot_data(df: list[dict]) -> dict:
    """
    Generate graph JSON payload used by frontend chart.
    """
    if not df:
        return {"dates": [], "price": [], "moving_avg": []}

    dates = [row["date"].strftime("%Y-%m-%d") for row in df]
    prices = [float(row["close"]) for row in df]
    moving_avg = []
    for idx in range(len(prices)):
        start = max(0, idx - 4)
        window = prices[start : idx + 1]
        moving_avg.append(sum(window) / len(window))

    return {
        "dates": dates,
        "price": [round(value, 2) for value in prices],
        "moving_avg": [round(value, 2) for value in moving_avg],
    }
