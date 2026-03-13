import logging
import signal
import sys
import time

from app.config import Config
from app.kinesis_writer import KinesisWriter
from app.news_client import NewsClient
from app.processor import process_articles

logger = logging.getLogger(__name__)

_running = True


def _shutdown_handler(signum: int, _frame) -> None:
    global _running
    sig_name = signal.Signals(signum).name
    logger.info("Received %s — shutting down gracefully…", sig_name)
    _running = False


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def run() -> None:
    _setup_logging()

    logger.info("=== Aurora Analytics — News Ingest Pipeline ===")

    Config.validate()
    Config.log_summary()

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    news_client = NewsClient()
    kinesis_writer = KinesisWriter()

    logger.info("Starting polling loop (every %ds)…", Config.POLL_INTERVAL_SECONDS)

    while _running:
        try:
            raw_articles = news_client.fetch_articles()

            new_articles = news_client.deduplicate(raw_articles)

            if not new_articles:
                logger.info("No new articles this cycle. Sleeping…")
            else:
                processed = process_articles(new_articles)
                written = kinesis_writer.write(processed)
                logger.info(
                    "Cycle complete: %d fetched, %d new, %d processed, %d written",
                    len(raw_articles),
                    len(new_articles),
                    len(processed),
                    written,
                )

        except Exception:
            logger.exception("Unexpected error during poll cycle")

        for _ in range(Config.POLL_INTERVAL_SECONDS):
            if not _running:
                break
            time.sleep(1)

    logger.info("Pipeline stopped.")


if __name__ == "__main__":
    run()
