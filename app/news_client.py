import logging
import time
from collections import OrderedDict
from typing import Any

import requests

from app.config import Config

logger = logging.getLogger(__name__)

MAX_SEEN_URLS = 5000
MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds


class NewsClient:
    """Fetches articles from the NewsAPI Everything endpoint with
    retry logic and URL-based deduplication."""

    def __init__(self) -> None:
        self._seen_urls: OrderedDict[str, None] = OrderedDict()
        self._session = requests.Session()
        self._session.headers.update({"X-Api-Key": Config.NEWSAPI_KEY})

    def fetch_articles(self) -> list[dict[str, Any]]:
        """Fetch a page of articles from NewsAPI, retrying on transient errors."""
        params = {
            "q": Config.NEWSAPI_QUERY,
            "pageSize": Config.NEWSAPI_PAGE_SIZE,
            "sortBy": "publishedAt",
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._session.get(
                    Config.NEWSAPI_BASE_URL, params=params, timeout=15
                )

                if resp.status_code == 429:
                    wait = BACKOFF_BASE ** attempt
                    logger.warning("Rate-limited (429). Retrying in %ds…", wait)
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                if data.get("status") != "ok":
                    logger.error("NewsAPI error: %s", data.get("message", "unknown"))
                    return []

                articles = data.get("articles", [])
                logger.info("Fetched %d articles from NewsAPI", len(articles))
                return articles

            except requests.exceptions.Timeout:
                wait = BACKOFF_BASE ** attempt
                logger.warning(
                    "Request timed out (attempt %d/%d). Retrying in %ds…",
                    attempt, MAX_RETRIES, wait,
                )
                time.sleep(wait)

            except requests.exceptions.RequestException as exc:
                wait = BACKOFF_BASE ** attempt
                logger.error(
                    "Request failed (attempt %d/%d): %s. Retrying in %ds…",
                    attempt, MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)

        logger.error("All %d retry attempts exhausted. Skipping this cycle.", MAX_RETRIES)
        return []

    def deduplicate(self, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter out articles whose URL has already been seen."""
        new_articles: list[dict[str, Any]] = []

        for article in articles:
            url = article.get("url")
            if not url or url in self._seen_urls:
                continue

            self._seen_urls[url] = None
            new_articles.append(article)

            # Evict oldest entries when cache exceeds limit
            while len(self._seen_urls) > MAX_SEEN_URLS:
                self._seen_urls.popitem(last=False)

        skipped = len(articles) - len(new_articles)
        if skipped:
            logger.info("Deduplication: %d new, %d skipped", len(new_articles), skipped)

        return new_articles
