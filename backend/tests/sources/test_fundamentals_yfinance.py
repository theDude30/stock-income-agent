import pandas as pd

from app.sources.fundamentals_yfinance import YFinanceFundamentalsSource


class _FakeTicker:
    def __init__(self, ticker):
        cols = [pd.Timestamp("2026-03-31")]
        self.quarterly_income_stmt = pd.DataFrame(
            {cols[0]: {"Total Revenue": 100.0, "Net Income": 20.0, "Diluted EPS": 2.0}}
        )
        self.quarterly_cashflow = pd.DataFrame(
            {cols[0]: {"Free Cash Flow": 30.0, "Cash Dividends Paid": -10.0}}
        )
        self.quarterly_balance_sheet = pd.DataFrame(
            {cols[0]: {"Total Debt": 50.0, "Stockholders Equity": 80.0}}
        )


def test_yf_fundamentals_normalizes():
    src = YFinanceFundamentalsSource(ticker_factory=_FakeTicker)
    snaps = list(src.fetch("KO"))
    assert len(snaps) == 1
    s = snaps[0]
    assert s.fiscal_period == "2026Q1"
    assert s.revenue == 100.0
    assert s.net_income == 20.0
    assert s.fcf == 30.0
    assert s.dividends_paid == 10.0  # absolute value
    assert s.total_debt == 50.0
    assert s.total_equity == 80.0
