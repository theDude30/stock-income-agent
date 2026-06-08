from collections.abc import Callable, Iterable

import yfinance as yf

from app.sources.base import FundamentalsSnapshot


def _get(df, row_label, col):
    try:
        val = df.loc[row_label, col]
    except (KeyError, AttributeError):
        return None
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # drop NaN


def _fiscal_period(ts) -> str:
    q = (ts.month - 1) // 3 + 1
    return f"{ts.year}Q{q}"


class YFinanceFundamentalsSource:
    def __init__(self, ticker_factory: Callable[[str], object] = yf.Ticker) -> None:
        self._ticker_factory = ticker_factory

    def fetch(self, ticker: str) -> Iterable[FundamentalsSnapshot]:
        t = self._ticker_factory(ticker)
        income = getattr(t, "quarterly_income_stmt", None)
        cashflow = getattr(t, "quarterly_cashflow", None)
        balance = getattr(t, "quarterly_balance_sheet", None)
        if income is None or income.empty:
            return []

        out: list[FundamentalsSnapshot] = []
        for col in income.columns:
            divs = _get(cashflow, "Cash Dividends Paid", col)
            out.append(FundamentalsSnapshot(
                fiscal_period=_fiscal_period(col),
                revenue=_get(income, "Total Revenue", col),
                eps=_get(income, "Diluted EPS", col),
                fcf=_get(cashflow, "Free Cash Flow", col),
                net_income=_get(income, "Net Income", col),
                total_debt=_get(balance, "Total Debt", col),
                total_equity=_get(balance, "Stockholders Equity", col),
                dividends_paid=abs(divs) if divs is not None else None,
            ))
        return out
