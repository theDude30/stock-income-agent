from app.analysis.screener import (
    ScreenerSignals,
    compute_debt_to_equity,
    compute_fcf_coverage,
    compute_payout_ratio,
    compute_quality_score,
    compute_ttm_yield,
)


def test_ttm_yield():
    assert compute_ttm_yield(2.0, 50.0) == 0.04
    assert compute_ttm_yield(2.0, 0.0) is None
    assert compute_ttm_yield(2.0, None) is None


def test_payout_ratio():
    assert compute_payout_ratio(10.0, 20.0) == 0.5
    assert compute_payout_ratio(10.0, 0.0) is None
    assert compute_payout_ratio(10.0, None) is None


def test_fcf_coverage():
    assert compute_fcf_coverage(30.0, 10.0) == 3.0
    assert compute_fcf_coverage(30.0, 0.0) is None


def test_debt_to_equity():
    assert compute_debt_to_equity(50.0, 100.0) == 0.5
    assert compute_debt_to_equity(50.0, 0.0) is None


def test_quality_score_rewards_safe_dividend():
    safe = ScreenerSignals(
        ttm_yield=0.04, payout_ratio=0.4, fcf_coverage=3.0,
        debt_to_equity=0.3, consecutive_years_paid=30, earnings_growth_5y=0.08,
    )
    risky = ScreenerSignals(
        ttm_yield=0.09, payout_ratio=0.95, fcf_coverage=0.8,
        debt_to_equity=3.0, consecutive_years_paid=1, earnings_growth_5y=-0.1,
    )
    assert compute_quality_score(safe) > compute_quality_score(risky)
    assert 0.0 <= compute_quality_score(safe) <= 100.0
    assert 0.0 <= compute_quality_score(risky) <= 100.0


def test_quality_score_handles_missing_data():
    empty = ScreenerSignals(None, None, None, None, None, None)
    assert compute_quality_score(empty) == 0.0
