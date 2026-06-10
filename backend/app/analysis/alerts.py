"""Pure builders turning raw state into alert payload dicts. No DB, no network.

All Decimal money values are converted to float for JSON payloads.
"""
from collections import Counter
from datetime import date
from decimal import Decimal

SAFETY_DROP_THRESHOLD = 10


def build_safety_alert(ticker: str, current: int, previous: int,
                       concerns: list[str]) -> dict | None:
    drop = previous - current
    if drop <= SAFETY_DROP_THRESHOLD:
        return None
    return {"ticker": ticker, "current_score": current, "previous_score": previous,
            "drop": drop, "concerns": concerns}


def build_dividend_upcoming(ticker: str, ex_date: date, amount_per_share: Decimal,
                            shares: Decimal) -> dict:
    return {"ticker": ticker, "ex_date": ex_date.isoformat(),
            "amount_per_share": float(amount_per_share), "shares": float(shares),
            "expected_amount": float(amount_per_share * shares)}


def build_call_expiring(pos, today: date) -> dict:
    return {"ticker": pos.ticker, "strike": float(pos.strike),
            "expiration_date": pos.expiration_date.isoformat(),
            "days_to_expiry": (pos.expiration_date - today).days}


def build_new_recs_summary(recs: list) -> dict | None:
    if not recs:
        return None
    by_type = Counter(r.type for r in recs)
    return {"count": len(recs), "by_type": dict(by_type), "ids": [r.id for r in recs]}


def build_monthly_summary(income_events: list, closed_feedback: list, month: str) -> dict:
    by_type: dict[str, float] = {}
    total = Decimal("0")
    for ie in income_events:
        total += ie.amount
        by_type[ie.type] = by_type.get(ie.type, 0.0) + float(ie.amount)
    wins = sum(1 for f in closed_feedback if f.outcome == "win")
    losses = sum(1 for f in closed_feedback if f.outcome == "loss")
    return {"month": month, "total_income": float(total), "by_type": by_type,
            "positions_closed": len(closed_feedback), "wins": wins, "losses": losses}
