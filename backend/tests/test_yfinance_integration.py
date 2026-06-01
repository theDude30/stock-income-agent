from datetime import date, timedelta

import pytest


@pytest.mark.slow
def test_yfinance_prices_returns_data_for_known_ticker():
    from app.sources.yfinance_source import YFinancePriceSource

    bars = list(
        YFinancePriceSource().fetch("KO", since=date.today() - timedelta(days=30))
    )
    assert len(bars) >= 5, f"expected at least 5 bars in last 30 days, got {len(bars)}"
    assert all(b.open > 0 for b in bars)


@pytest.mark.slow
def test_yfinance_dividends_returns_data_for_known_ticker():
    from app.sources.yfinance_source import YFinanceDividendSource

    events = list(
        YFinanceDividendSource().fetch("KO", since=date.today() - timedelta(days=400))
    )
    assert len(events) >= 1, "KO should have at least one dividend in the last 400 days"


@pytest.mark.slow
def test_yahoo_rss_returns_items_for_known_ticker():
    from app.sources.yahoo_rss_source import YahooRssNewsSource

    items = list(YahooRssNewsSource().fetch("KO", since=None))
    assert len(items) >= 1
    assert items[0].url.startswith("http")


@pytest.mark.slow
def test_wikipedia_sp500_returns_around_500_tickers():
    from app.sources.wikipedia_source import WikipediaSP500Source

    stocks = list(WikipediaSP500Source().fetch_sp500())
    assert 480 <= len(stocks) <= 520, f"expected ~500, got {len(stocks)}"
    assert all(s.ticker for s in stocks)
