from __future__ import annotations

from datetime import datetime


def clean_data(df: list[dict]) -> list[dict]:
    """
    Clean and standardize live stock price rows.
    """
    cleaned: list[dict] = []
    for row in df:
        date_str = row.get("date")
        close = row.get("close")
        if date_str is None or close is None:
            continue
        try:
            parsed_date = datetime.strptime(str(date_str), "%Y-%m-%d").date()
            parsed_close = float(close)
        except (TypeError, ValueError):
            continue
        cleaned.append(
            {
                "date": parsed_date,
                "close": parsed_close,
            }
        )
    return sorted(cleaned, key=lambda value: value["date"])
