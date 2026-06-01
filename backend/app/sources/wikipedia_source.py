from collections.abc import Iterable
from io import StringIO

import httpx
import pandas as pd

from app.sources.base import StockMeta

SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
USER_AGENT = "stock-income-agent/0.1 (https://github.com/theDude30/stock-income-agent; personal research)"


class WikipediaSP500Source:
    def __init__(self, url: str = SP500_WIKI_URL) -> None:
        self.url = url

    def fetch_sp500(self) -> Iterable[StockMeta]:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as client:
            response = client.get(self.url)
            response.raise_for_status()
        # The first table on the page is the constituents list.
        tables = pd.read_html(StringIO(response.text))
        df = tables[0]
        for _, row in df.iterrows():
            ticker = str(row["Symbol"]).replace(".", "-")  # yfinance uses BRK-B not BRK.B
            yield StockMeta(
                ticker=ticker,
                name=str(row["Security"]),
                sector=str(row["GICS Sector"]) if pd.notna(row["GICS Sector"]) else None,
                industry=str(row["GICS Sub-Industry"]) if pd.notna(row["GICS Sub-Industry"]) else None,
            )
