from collections.abc import Iterable
from datetime import UTC, datetime
from time import mktime

import feedparser

from app.sources.base import NewsItemDTO

YAHOO_RSS_URL_TEMPLATE = "https://finance.yahoo.com/rss/headline?s={ticker}"


class YahooRssNewsSource:
    def __init__(self, url_template: str = YAHOO_RSS_URL_TEMPLATE) -> None:
        self.url_template = url_template

    def fetch(self, ticker: str, since: datetime | None) -> Iterable[NewsItemDTO]:
        feed = feedparser.parse(self.url_template.format(ticker=ticker))
        for entry in feed.entries:
            published_at = self._parse_dt(entry)
            if since is not None and published_at < since:
                continue
            yield NewsItemDTO(
                url=str(entry.get("link", "")).strip(),
                title=str(entry.get("title", "")),
                summary=str(entry.get("summary", "")),
                source="yahoo",
                published_at=published_at,
            )

    def _parse_dt(self, entry) -> datetime:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed is not None:
            return datetime.fromtimestamp(mktime(parsed), tz=UTC)
        return datetime.now(tz=UTC)
