from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.sources.base import OptionsChainRow


@dataclass(frozen=True)
class CandidateCall:
    strike: float
    premium: float
    iv: float | None
    expiration_date: date


@dataclass(frozen=True)
class ScoredCall:
    candidate: CandidateCall
    premium_yield: float
    prob_assignment: float
    score: float


def filter_otm_calls(
    rows: Iterable[OptionsChainRow], price: float, min_pct: float = 0.03, max_pct: float = 0.07
) -> list[CandidateCall]:
    out: list[CandidateCall] = []
    for r in rows:
        if r.option_type != "call":
            continue
        moneyness = (r.strike - price) / price
        if min_pct <= moneyness <= max_pct:
            premium = r.bid if r.bid is not None else (r.last or 0.0)
            out.append(CandidateCall(strike=r.strike, premium=premium, iv=r.implied_volatility,
                                     expiration_date=r.expiration_date))
    return out


def _prob_assignment(strike: float, price: float, iv: float | None) -> float:
    """Rough proxy: closer-to-the-money and higher-IV calls are likelier to be assigned.
    Bounded 0-1. Not Black-Scholes; good enough for ranking."""
    moneyness = (strike - price) / price  # positive for OTM
    iv = iv if iv else 0.3
    raw = 0.5 - moneyness / (iv if iv > 0 else 0.3)
    return max(0.0, min(1.0, raw))


def score_call(c: CandidateCall, price: float) -> ScoredCall:
    premium_yield = c.premium / price if price else 0.0
    prob = _prob_assignment(c.strike, price, c.iv)
    # Reward premium income, penalize assignment probability (regret).
    score = premium_yield * 100.0 - prob * 2.0
    return ScoredCall(candidate=c, premium_yield=premium_yield, prob_assignment=prob, score=score)
