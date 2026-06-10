from datetime import date
from decimal import Decimal

from app.analysis.alerts import (
    build_call_expiring,
    build_dividend_upcoming,
    build_monthly_summary,
    build_new_recs_summary,
    build_safety_alert,
)


def test_build_safety_alert_only_above_threshold():
    assert build_safety_alert("KO", 60, 75, ["payout rising"]) == {
        "ticker": "KO", "current_score": 60, "previous_score": 75, "drop": 15,
        "concerns": ["payout rising"],
    }
    assert build_safety_alert("KO", 70, 75, []) is None       # drop of 5 <= 10
    assert build_safety_alert("KO", 80, 75, []) is None       # improvement


def test_build_dividend_upcoming():
    out = build_dividend_upcoming("JNJ", date(2026, 6, 12), Decimal("1.19"), Decimal("100"))
    assert out["ticker"] == "JNJ"
    assert out["ex_date"] == "2026-06-12"
    assert out["expected_amount"] == 119.0


def test_build_call_expiring():
    class P:
        ticker = "KO"
        strike = Decimal("65")
        expiration_date = date(2026, 6, 12)
    out = build_call_expiring(P(), date(2026, 6, 9))
    assert out == {"ticker": "KO", "strike": 65.0,
                   "expiration_date": "2026-06-12", "days_to_expiry": 3}


def test_build_new_recs_summary_none_when_empty():
    assert build_new_recs_summary([]) is None


def test_build_new_recs_summary_counts_by_type():
    class R:
        def __init__(self, id, type):
            self.id = id
            self.type = type
    recs = [R(1, "add_position"), R(2, "add_position"), R(3, "sell_covered_call")]
    out = build_new_recs_summary(recs)
    assert out["count"] == 3
    assert out["by_type"]["add_position"] == 2
    assert out["by_type"]["sell_covered_call"] == 1
    assert set(out["ids"]) == {1, 2, 3}


def test_build_monthly_summary():
    class IE:
        def __init__(self, type, amount):
            self.type = type
            self.amount = amount
    class FB:
        def __init__(self, outcome):
            self.outcome = outcome
    income = [IE("dividend", Decimal("50")), IE("call_premium", Decimal("120"))]
    fb = [FB("win"), FB("win"), FB("loss")]
    out = build_monthly_summary(income, fb, "2026-05")
    assert out["month"] == "2026-05"
    assert out["total_income"] == 170.0
    assert out["by_type"] == {"dividend": 50.0, "call_premium": 120.0}
    assert out["positions_closed"] == 3
    assert out["wins"] == 2 and out["losses"] == 1
