from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market.price_cache import PriceCache


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 6, 11, 14, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now = self.now + timedelta(seconds=seconds)


class CountingFetch:
    def __init__(self, price: Decimal) -> None:
        self.price = price
        self.calls: list[str] = []

    def __call__(self, ticker: str) -> Decimal:
        self.calls.append(ticker)
        return self.price


async def test_first_get_fetches_and_returns_price_with_timestamp():
    clock = FakeClock()
    fetch = CountingFetch(Decimal("61.50"))
    cache = PriceCache(fetch=fetch, now=clock)

    price, as_of = await cache.get("KO")

    assert price == Decimal("61.50")
    assert as_of == clock.now
    assert fetch.calls == ["KO"]


async def test_second_get_within_ttl_uses_cache():
    clock = FakeClock()
    fetch = CountingFetch(Decimal("61.50"))
    cache = PriceCache(fetch=fetch, now=clock)

    first = await cache.get("KO")
    clock.advance(119)
    second = await cache.get("KO")

    assert second == first  # same price AND same as_of timestamp
    assert fetch.calls == ["KO"]  # only one real fetch


async def test_get_after_ttl_refetches():
    clock = FakeClock()
    fetch = CountingFetch(Decimal("61.50"))
    cache = PriceCache(fetch=fetch, now=clock)

    await cache.get("KO")
    clock.advance(120)  # exactly TTL → expired
    fetch.price = Decimal("62.00")
    price, as_of = await cache.get("KO")

    assert price == Decimal("62.00")
    assert as_of == clock.now
    assert fetch.calls == ["KO", "KO"]


async def test_tickers_are_cached_independently():
    clock = FakeClock()
    fetch = CountingFetch(Decimal("100"))
    cache = PriceCache(fetch=fetch, now=clock)

    await cache.get("KO")
    await cache.get("PEP")
    await cache.get("KO")

    assert fetch.calls == ["KO", "PEP"]


async def test_fetch_failure_propagates_and_is_not_cached():
    clock = FakeClock()
    calls: list[str] = []

    def failing_fetch(ticker: str) -> Decimal:
        calls.append(ticker)
        raise LookupError("no data")

    cache = PriceCache(fetch=failing_fetch, now=clock)

    with pytest.raises(LookupError):
        await cache.get("KO")
    with pytest.raises(LookupError):
        await cache.get("KO")  # not cached → fetch attempted again

    assert calls == ["KO", "KO"]


async def test_default_clock_is_utc_now():
    cache = PriceCache(fetch=lambda t: Decimal("1"))
    _, as_of = await cache.get("KO")
    assert as_of.tzinfo is not None
