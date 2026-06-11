import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal


class PriceCache:
    """Per-ticker live-price cache with a TTL (default 120 s, design spec 5b §2).

    Wraps a synchronous fetch callable (yfinance is sync) and runs it in a
    thread so async endpoints don't block the event loop. Fetch failures
    propagate to the caller and are never cached.
    """

    def __init__(
        self,
        fetch: Callable[[str], Decimal],
        now: Callable[[], datetime] | None = None,
        ttl_seconds: int = 120,
    ) -> None:
        self._fetch = fetch
        self._now = now if now is not None else (lambda: datetime.now(tz=UTC))
        self._ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[Decimal, datetime]] = {}

    async def get(self, ticker: str) -> tuple[Decimal, datetime]:
        """Return (price, as_of). Serves from cache while the entry is younger than the TTL."""
        cached = self._cache.get(ticker)
        now = self._now()
        if cached is not None and (now - cached[1]).total_seconds() < self._ttl_seconds:
            return cached
        price = await asyncio.to_thread(self._fetch, ticker)
        entry = (price, now)
        self._cache[ticker] = entry
        return entry
