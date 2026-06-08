from collections.abc import Iterable
from datetime import date, datetime

from app.sources.base import (
    DividendEvent,
    FundamentalsSnapshot,
    NewsItemDTO,
    OptionsChainRow,
    PriceBar,
    StockMeta,
)


class InMemoryUniverseSource:
    def __init__(self, stocks: Iterable[StockMeta]) -> None:
        self._stocks = list(stocks)

    def fetch_sp500(self) -> Iterable[StockMeta]:
        return list(self._stocks)


class InMemoryPriceSource:
    def __init__(self, bars: dict[str, list[PriceBar]]) -> None:
        self._bars = bars

    def fetch(self, ticker: str, since: date | None) -> Iterable[PriceBar]:
        rows = self._bars[ticker]
        if since is None:
            return list(rows)
        return [b for b in rows if b.date >= since]


class InMemoryDividendSource:
    def __init__(self, events: dict[str, list[DividendEvent]]) -> None:
        self._events = events

    def fetch(self, ticker: str, since: date | None) -> Iterable[DividendEvent]:
        rows = self._events.get(ticker, [])
        if since is None:
            return list(rows)
        return [d for d in rows if d.ex_date >= since]


class InMemoryOptionsSource:
    def __init__(self, chains: dict[str, list[OptionsChainRow]]) -> None:
        self._chains = chains

    def fetch(self, ticker: str, expirations_within_days: int = 60) -> Iterable[OptionsChainRow]:
        return list(self._chains.get(ticker, []))


class InMemoryNewsSource:
    def __init__(self, items: dict[str, list[NewsItemDTO]]) -> None:
        self._items = items

    def fetch(self, ticker: str, since: datetime | None) -> Iterable[NewsItemDTO]:
        rows = self._items.get(ticker, [])
        if since is None:
            return list(rows)
        return [n for n in rows if n.published_at >= since]


class InMemoryFundamentalsSource:
    def __init__(self, data: dict[str, list[FundamentalsSnapshot]]) -> None:
        self._data = data

    def fetch(self, ticker: str) -> Iterable[FundamentalsSnapshot]:
        return list(self._data.get(ticker, []))
