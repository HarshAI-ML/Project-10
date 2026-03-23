from __future__ import annotations


def opportunity_engine(pe_ratio: float, discount_level: str) -> float:
    """
    Compute opportunity score from precomputed indicators.
    """
    discount_bonus = {
        "HIGH": 30.0,
        "MEDIUM": 18.0,
        "LOW": 8.0,
        "UNKNOWN": 0.0,
    }.get(discount_level, 0.0)
    pe_component = max(0.0, 40.0 - (pe_ratio * 1.3))
    raw_score = 30.0 + discount_bonus + pe_component
    return round(min(raw_score, 100.0), 2)
