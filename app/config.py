import os
import sys
import logging
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Config:
    """Central configuration loaded from environment variables."""

    NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")
    NEWSAPI_BASE_URL: str = os.getenv("NEWSAPI_BASE_URL", "https://newsapi.org/v2/everything")
    NEWSAPI_QUERY: str = os.getenv("NEWSAPI_QUERY", "technology")
    NEWSAPI_PAGE_SIZE: int = int(os.getenv("NEWSAPI_PAGE_SIZE", "50"))

    AWS_REGION: str = os.getenv("AWS_REGION", "ap-southeast-1")
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_ENDPOINT_URL: str = os.getenv("AWS_ENDPOINT_URL", "")
    KINESIS_STREAM_NAME: str = os.getenv("KINESIS_STREAM_NAME", "aurora-news-stream")

    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

    _REQUIRED = [
        ("NEWSAPI_KEY", "NewsAPI API key"),
        ("AWS_ACCESS_KEY_ID", "AWS access key ID"),
        ("AWS_SECRET_ACCESS_KEY", "AWS secret access key"),
        ("KINESIS_STREAM_NAME", "Kinesis stream name"),
    ]

    @classmethod
    def validate(cls) -> None:
        """Fail fast if any required variable is missing or still a placeholder."""
        missing: list[str] = []
        for attr, label in cls._REQUIRED:
            value = getattr(cls, attr, "")
            if not value or value.startswith("your_"):
                missing.append(f"  - {attr} ({label})")

        if missing:
            logger.error("Missing required environment variables:\n%s", "\n".join(missing))
            sys.exit(1)

    @classmethod
    def log_summary(cls) -> None:
        """Log non-secret settings at startup."""
        logger.info("--- Configuration ---")
        logger.info("  NEWSAPI_BASE_URL   = %s", cls.NEWSAPI_BASE_URL)
        logger.info("  NEWSAPI_QUERY      = %s", cls.NEWSAPI_QUERY)
        logger.info("  NEWSAPI_PAGE_SIZE  = %d", cls.NEWSAPI_PAGE_SIZE)
        logger.info("  AWS_REGION         = %s", cls.AWS_REGION)
        logger.info("  KINESIS_STREAM     = %s", cls.KINESIS_STREAM_NAME)
        logger.info("  POLL_INTERVAL      = %ds", cls.POLL_INTERVAL_SECONDS)
        logger.info("  NEWSAPI_KEY        = %s", cls.NEWSAPI_KEY[:4] + "****")
        logger.info("---------------------")
