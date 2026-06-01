from datetime import UTC, date, datetime

import pytest

from app.sources.base import DividendEvent, NewsItemDTO, OptionsChainRow, PriceBar, StockMeta


def test_inmemory_universe_returns_seeded_tickers():
    from app.sources.fakes import InMemoryUniverseSource

    src = InMemoryUniverseSource(
        [
            StockMeta("AAPL", "Apple", "Tech", "Consumer Electronics"),
            StockMeta("MSFT", "Microsoft", "Tech", "Software"),
        ]
    )
    out = list(src.fetch_sp500())
    assert [s.ticker for s in out] == ["AAPL", "MSFT"]


def test_inmemory_prices_returns_only_since_date():
    from app.sources.fakes import InMemoryPriceSource

    bars = {
        "AAPL": [
            PriceBar(date(2026, 1, 1), 100.0, 101.0, 99.0, 100.5, 100.5, 1000),
            PriceBar(date(2026, 1, 2), 100.5, 102.0, 100.0, 101.0, 101.0, 1500),
            PriceBar(date(2026, 1, 3), 101.0, 103.0, 100.5, 102.0, 102.0, 2000),
        ]
    }
    src = InMemoryPriceSource(bars)
    out = list(src.fetch("AAPL", since=date(2026, 1, 2)))
    assert [b.date for b in out] == [date(2026, 1, 2), date(2026, 1, 3)]


def test_inmemory_prices_unknown_ticker_raises():
    from app.sources.fakes import InMemoryPriceSource

    src = InMemoryPriceSource({"AAPL": []})
    with pytest.raises(KeyError):
        list(src.fetch("UNKNOWN", since=None))


def test_inmemory_dividends_returns_only_since_date():
    from app.sources.fakes import InMemoryDividendSource

    src = InMemoryDividendSource(
        {
            "KO": [
                DividendEvent(date(2026, 1, 15), date(2026, 2, 1), 0.46),
                DividendEvent(date(2026, 4, 15), date(2026, 5, 1), 0.46),
            ]
        }
    )
    out = list(src.fetch("KO", since=date(2026, 3, 1)))
    assert [d.ex_date for d in out] == [date(2026, 4, 15)]


def test_inmemory_options_returns_seeded_chain():
    from app.sources.fakes import InMemoryOptionsSource

    src = InMemoryOptionsSource(
        {
            "AAPL": [
                OptionsChainRow(date(2026, 7, 17), 200.0, "call", 5.0, 5.1, 5.05, 0.25, 100, 500),
            ]
        }
    )
    out = list(src.fetch("AAPL"))
    assert len(out) == 1
    assert out[0].strike == 200.0


def test_inmemory_news_returns_seeded_items_filtered_by_since():
    from app.sources.fakes import InMemoryNewsSource

    src = InMemoryNewsSource(
        {
            "AAPL": [
                NewsItemDTO("https://a.example/1", "T1", "S1", "yahoo", datetime(2026, 1, 1, tzinfo=UTC)),
                NewsItemDTO("https://a.example/2", "T2", "S2", "yahoo", datetime(2026, 1, 2, tzinfo=UTC)),
            ]
        }
    )
    out = list(src.fetch("AAPL", since=datetime(2026, 1, 2, tzinfo=UTC)))
    assert [n.url for n in out] == ["https://a.example/2"]
