import json
import logging
import time

import boto3
from botocore.exceptions import ClientError

from app.config import Config
from app.processor import Article

logger = logging.getLogger(__name__)

KINESIS_MAX_BATCH = 500
MAX_RETRIES = 3
BACKOFF_BASE = 2


class KinesisWriter:
    """Writes Article records to an AWS Kinesis Data Stream in batches."""

    def __init__(self) -> None:
        kwargs: dict = {
            "region_name": Config.AWS_REGION,
            "aws_access_key_id": Config.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": Config.AWS_SECRET_ACCESS_KEY,
        }
        if Config.AWS_ENDPOINT_URL:
            kwargs["endpoint_url"] = Config.AWS_ENDPOINT_URL
        self._client = boto3.client("kinesis", **kwargs)
        self._stream_name = Config.KINESIS_STREAM_NAME

    def write(self, articles: list[Article]) -> int:
        """Write articles to Kinesis in batches. Returns total successful count."""
        if not articles:
            return 0

        total_success = 0

        for i in range(0, len(articles), KINESIS_MAX_BATCH):
            batch = articles[i : i + KINESIS_MAX_BATCH]
            records = [
                {
                    "Data": json.dumps(article.model_dump()).encode("utf-8"),
                    "PartitionKey": article.article_id,
                }
                for article in batch
            ]
            success = self._put_records_with_retry(records)
            total_success += success

        logger.info(
            "Kinesis write complete: %d/%d records succeeded",
            total_success, len(articles),
        )
        return total_success

    def _put_records_with_retry(self, records: list[dict]) -> int:
        """Send a batch to Kinesis, retrying failed records with backoff."""
        pending = records
        total_ok = 0

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._client.put_records(
                    StreamName=self._stream_name, Records=pending
                )
            except ClientError as exc:
                error_code = exc.response["Error"]["Code"]
                if error_code == "ProvisionedThroughputExceededException":
                    wait = BACKOFF_BASE ** attempt
                    logger.warning(
                        "Throughput exceeded (attempt %d/%d). Retrying in %ds…",
                        attempt, MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                    continue
                logger.error("Kinesis ClientError: %s", exc)
                break

            failed_count = response.get("FailedRecordCount", 0)
            succeeded = len(pending) - failed_count
            total_ok += succeeded

            if failed_count == 0:
                break

            # Collect only the failed records for retry
            retry_records = []
            for record, result in zip(pending, response["Records"]):
                if "ErrorCode" in result:
                    retry_records.append(record)

            logger.warning(
                "%d records failed (attempt %d/%d). Retrying…",
                failed_count, attempt, MAX_RETRIES,
            )
            pending = retry_records
            time.sleep(BACKOFF_BASE ** attempt)

        return total_ok
