from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenerSignals:
    ttm_yield: float | None
    payout_ratio: float | None
    fcf_coverage: float | None
    debt_to_equity: float | None
    consecutive_years_paid: int | None
    earnings_growth_5y: float | None


def compute_ttm_yield(ttm_dividends: float | None, price: float | None) -> float | None:
    if not ttm_dividends or not price:
        return None
    return ttm_dividends / price


def compute_payout_ratio(dividends_paid: float | None, net_income: float | None) -> float | None:
    if dividends_paid is None or not net_income:
        return None
    return dividends_paid / net_income


def compute_fcf_coverage(fcf: float | None, dividends_paid: float | None) -> float | None:
    if fcf is None or not dividends_paid:
        return None
    return fcf / dividends_paid


def compute_debt_to_equity(total_debt: float | None, total_equity: float | None) -> float | None:
    if total_debt is None or not total_equity:
        return None
    return total_debt / total_equity


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute_quality_score(s: ScreenerSignals) -> float:
    """Composite 0-100. Each sub-score is 0-1; weighted, scaled to 100.
    Missing inputs contribute 0 to their component."""
    # Payout ratio: best at/below 0.5, unsustainable above ~0.7.
    payout = 0.0 if s.payout_ratio is None else _clamp(1.0 - (s.payout_ratio - 0.5) / 0.5) if s.payout_ratio > 0.5 else 1.0
    # FCF coverage: safe at >= 1.5; linear up to 1.5.
    coverage = 0.0 if s.fcf_coverage is None else _clamp(s.fcf_coverage / 1.5)
    # Debt/equity: lower is better; 0 -> 1, >= 2 -> 0.
    leverage = 0.0 if s.debt_to_equity is None else _clamp(1.0 - s.debt_to_equity / 2.0)
    # Track record: 25 years -> 1.0.
    track = 0.0 if s.consecutive_years_paid is None else _clamp(s.consecutive_years_paid / 25.0)
    # Growth: -10% -> 0, +10% -> 1.
    growth = 0.0 if s.earnings_growth_5y is None else _clamp((s.earnings_growth_5y + 0.1) / 0.2)

    weighted = 0.30 * payout + 0.25 * coverage + 0.20 * leverage + 0.15 * track + 0.10 * growth
    return round(weighted * 100.0, 2)
