from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol


@dataclass(frozen=True)
class StockMeta:
    ticker: str
    name: str
    sector: str | None
    industry: str | None


@dataclass(frozen=True)
class PriceBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: int


@dataclass(frozen=True)
class DividendEvent:
    ex_date: date
    pay_date: date | None
    amount_per_share: float


@dataclass(frozen=True)
class OptionsChainRow:
    expiration_date: date
    strike: float
    option_type: Literal["call", "put"]
    bid: float | None
    ask: float | None
    last: float | None
    implied_volatility: float | None
    volume: int | None
    open_interest: int | None


@dataclass(frozen=True)
class NewsItemDTO:
    url: str
    title: str
    summary: str
    source: str
    published_at: datetime


@dataclass(frozen=True)
class FundamentalsSnapshot:
    fiscal_period: str
    revenue: float | None
    eps: float | None
    fcf: float | None
    net_income: float | None
    total_debt: float | None
    total_equity: float | None
    dividends_paid: float | None


class UniverseSource(Protocol):
    def fetch_sp500(self) -> Iterable[StockMeta]: ...


class PriceSource(Protocol):
    def fetch(self, ticker: str, since: date | None) -> Iterable[PriceBar]: ...


class DividendSource(Protocol):
    def fetch(self, ticker: str, since: date | None) -> Iterable[DividendEvent]: ...


class OptionsSource(Protocol):
    def fetch(self, ticker: str, expirations_within_days: int = 60) -> Iterable[OptionsChainRow]: ...


class NewsSource(Protocol):
    def fetch(self, ticker: str, since: datetime | None) -> Iterable[NewsItemDTO]: ...


class FundamentalsSource(Protocol):
    def fetch(self, ticker: str) -> Iterable[FundamentalsSnapshot]: ...


@dataclass
class Sources:
    universe: UniverseSource
    prices: PriceSource
    dividends: DividendSource
    options: OptionsSource
    news: NewsSource
    fundamentals: "FundamentalsSource | None" = None
