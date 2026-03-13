import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

TRUNCATION_PATTERN = re.compile(r"\s*\[\+\d+ chars]$")


class Article(BaseModel):
    """Validated article schema matching the Kinesis output contract."""

    article_id: str
    source_name: str
    title: str
    content: str
    url: str
    author: str
    published_at: str
    ingested_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("content", mode="before")
    @classmethod
    def clean_content(cls, v: str | None) -> str:
        if not v:
            return ""
        return TRUNCATION_PATTERN.sub("", v).strip()

    @field_validator("published_at", mode="before")
    @classmethod
    def normalize_timestamp(cls, v: str | None) -> str:
        if not v:
            return ""
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt.isoformat()
        except (ValueError, TypeError):
            return v


def _generate_article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def process_articles(raw_articles: list[dict[str, Any]]) -> list[Article]:
    """Map, clean, and validate raw API responses into Article objects."""
    processed: list[Article] = []

    for raw in raw_articles:
        try:
            article = Article(
                article_id=_generate_article_id(raw.get("url", "")),
                source_name=(raw.get("source") or {}).get("name", "Unknown"),
                title=raw.get("title") or "Untitled",
                content=raw.get("content") or "",
                url=raw.get("url", ""),
                author=raw.get("author") or "Unknown",
                published_at=raw.get("publishedAt") or "",
            )
            processed.append(article)
        except Exception as exc:
            logger.warning("Skipping invalid article: %s — %s", raw.get("title", "?"), exc)

    logger.info("Processed %d/%d articles", len(processed), len(raw_articles))
    return processed
