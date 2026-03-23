from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from portfolio.models import Stock


def _to_records_frame(rows: Any) -> pd.DataFrame:
    """Build a DataFrame from row-like inputs without scalar constructor errors."""
    if rows is None:
        return pd.DataFrame()
    if isinstance(rows, dict):
        rows = [rows]
    elif not isinstance(rows, list):
        rows = list(rows)

    normalized: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            normalized.append(row)
        else:
            normalized.append({"value": row})
    return pd.DataFrame.from_records(normalized)


def export_portfolio_stocks_to_csv_and_json(
    portfolio_id: int,
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    Fetch all stocks for a portfolio, store them in a DataFrame, save as CSV,
    and print stocks data as JSON in terminal.
    """
    queryset = Stock.objects.filter(portfolio_id=portfolio_id).values(
        "id",
        "portfolio_id",
        "symbol",
        "company_name",
        "sector",
        "current_price",
        "predicted_price_1d",
        "expected_change_pct",
        "direction_signal",
        "model_confidence_r2",
        "prediction_status",
        "recommended_action",
        "prediction_updated_at",
    )
    rows = list(queryset)
    df = _to_records_frame(rows)

    if output_path:
        csv_path = Path(output_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        base_dir = Path(__file__).resolve().parents[1] / "dataframes"
        base_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = base_dir / f"portfolio_{portfolio_id}_stocks_{timestamp}.csv"

    df.to_csv(csv_path, index=False)

    print(json.dumps(rows, indent=2, default=str))
    print(f"CSV saved: {csv_path}")

    return {
        "portfolio_id": portfolio_id,
        "count": len(rows),
        "csv_path": str(csv_path),
        "rows": rows,
    }
