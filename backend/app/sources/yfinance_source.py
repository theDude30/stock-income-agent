from collections.abc import Iterable
from datetime import UTC, date, datetime

import yfinance as yf

from app.sources.base import DividendEvent, OptionsChainRow, PriceBar


class YFinancePriceSource:
    def fetch(self, ticker: str, since: date | None) -> Iterable[PriceBar]:
        t = yf.Ticker(ticker)
        kwargs: dict = {"auto_adjust": False, "actions": False}
        if since is not None:
            kwargs["start"] = since.isoformat()
        else:
            kwargs["period"] = "5y"
        df = t.history(**kwargs)
        for ts, row in df.iterrows():
            yield PriceBar(
                date=ts.date() if hasattr(ts, "date") else ts,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                adj_close=float(row.get("Adj Close", row["Close"])),
                volume=int(row["Volume"]),
            )


class YFinanceDividendSource:
    def fetch(self, ticker: str, since: date | None) -> Iterable[DividendEvent]:
        t = yf.Ticker(ticker)
        series = t.dividends  # pandas Series indexed by date
        for ts, amount in series.items():
            ex_date = ts.date() if hasattr(ts, "date") else ts
            if since is not None and ex_date < since:
                continue
            yield DividendEvent(ex_date=ex_date, pay_date=None, amount_per_share=float(amount))


class YFinanceOptionsSource:
    def fetch(
        self, ticker: str, expirations_within_days: int = 60
    ) -> Iterable[OptionsChainRow]:
        t = yf.Ticker(ticker)
        today = datetime.now(tz=UTC).date()
        for exp_str in (t.options or []):
            exp = datetime.strptime(exp_str, "%Y-%m-%d").date()
            if (exp - today).days > expirations_within_days:
                continue
            chain = t.option_chain(exp_str)
            for kind, df in (("call", chain.calls), ("put", chain.puts)):
                for _, row in df.iterrows():
                    yield OptionsChainRow(
                        expiration_date=exp,
                        strike=float(row["strike"]),
                        option_type=kind,
                        bid=_opt_float(row.get("bid")),
                        ask=_opt_float(row.get("ask")),
                        last=_opt_float(row.get("lastPrice")),
                        implied_volatility=_opt_float(row.get("impliedVolatility")),
                        volume=_opt_int(row.get("volume")),
                        open_interest=_opt_int(row.get("openInterest")),
                    )


def _opt_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN guard


def _opt_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
