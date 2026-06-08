from datetime import date

from app.analysis.options_scoring import CandidateCall, filter_otm_calls, score_call
from app.sources.base import OptionsChainRow


def _row(strike, opt_type="call", iv=0.3, bid=2.0, ask=2.2):
    return OptionsChainRow(
        expiration_date=date(2026, 7, 17), strike=strike, option_type=opt_type,
        bid=bid, ask=ask, last=2.1, implied_volatility=iv, volume=100, open_interest=500,
    )


def test_filter_otm_calls_keeps_3_to_7_pct():
    price = 100.0
    rows = [_row(95), _row(103), _row(105), _row(110), _row(103, opt_type="put")]
    out = filter_otm_calls(rows, price, min_pct=0.03, max_pct=0.07)
    strikes = sorted(c.strike for c in out)
    assert strikes == [103.0, 105.0]  # 95 ITM, 110 too far, put excluded


def test_score_call_prefers_higher_premium_yield():
    price = 100.0
    high = score_call(CandidateCall(strike=105.0, premium=3.0, iv=0.3,
                                    expiration_date=date(2026, 7, 17)), price)
    low = score_call(CandidateCall(strike=105.0, premium=1.0, iv=0.3,
                                   expiration_date=date(2026, 7, 17)), price)
    assert high.score > low.score
    assert 0.0 <= high.prob_assignment <= 1.0
