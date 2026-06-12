from decimal import Decimal

from app.analysis.portfolio import (
    classify_outcome,
    compute_assignment_gain,
    compute_capital_pnl,
    compute_covered_call_return_pct,
    compute_total_return_pct,
    is_call_itm,
)


def test_compute_capital_pnl():
    assert compute_capital_pnl(Decimal("50"), Decimal("60"), Decimal("100")) == Decimal("1000")
    assert compute_capital_pnl(Decimal("60"), Decimal("50"), Decimal("100")) == Decimal("-1000")


def test_compute_covered_call_return_pct():
    # $150 premium / $5000 cost basis = 3%
    assert compute_covered_call_return_pct(Decimal("150"), Decimal("5000")) == Decimal("0.03")
    assert compute_covered_call_return_pct(Decimal("150"), Decimal("0")) == Decimal("0")


def test_compute_total_return_pct():
    pct = compute_total_return_pct(
        capital_pnl=Decimal("500"),
        dividends=Decimal("100"),
        premiums=Decimal("50"),
        cost_basis=Decimal("5000"),
    )
    assert pct == Decimal("0.13")  # 650 / 5000
    assert compute_total_return_pct(Decimal("500"), Decimal("100"), Decimal("50"), Decimal("0")) == Decimal("0")


def test_classify_outcome():
    assert classify_outcome(Decimal("0.05")) == "win"
    assert classify_outcome(Decimal("-0.02")) == "loss"
    assert classify_outcome(Decimal("0")) == "breakeven"


def test_is_call_itm():
    assert is_call_itm(Decimal("50"), Decimal("50")) is True   # at the money = ITM for assignment
    assert is_call_itm(Decimal("50"), Decimal("51")) is True
    assert is_call_itm(Decimal("50"), Decimal("49")) is False


def test_compute_assignment_gain():
    # strike $55, entry $50, 100 shares → $500 gain
    assert compute_assignment_gain(Decimal("55"), Decimal("50"), Decimal("100")) == Decimal("500")
    # strike below entry → 0
    assert compute_assignment_gain(Decimal("48"), Decimal("50"), Decimal("100")) == Decimal("0")


def test_compute_adjusted_return_pct():
    from app.analysis.portfolio import compute_adjusted_return_pct
    # 100 → 105 adjusted = +5%
    assert compute_adjusted_return_pct(Decimal("100"), Decimal("105")) == Decimal("0.05")
    # guard: non-positive start
    assert compute_adjusted_return_pct(Decimal("0"), Decimal("105")) == Decimal("0")
