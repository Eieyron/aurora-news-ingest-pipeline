import json
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

from app.processor import Article
from app.kinesis_writer import KinesisWriter, KINESIS_MAX_BATCH


def _make_article(article_id="test123", url="https://example.com"):
    return Article(
        article_id=article_id,
        source_name="TestSource",
        title="Test Title",
        content="Test content",
        url=url,
        author="Author",
        published_at="2026-03-13T00:00:00+00:00",
    )


@pytest.fixture
def writer():
    with patch("app.kinesis_writer.boto3.client") as mock_boto:
        w = KinesisWriter()
        w._mock_client = mock_boto.return_value
        yield w


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("app.kinesis_writer.time.sleep"):
        yield


class TestWrite:
    def test_empty_list_returns_zero(self, writer):
        assert writer.write([]) == 0
        writer._mock_client.put_records.assert_not_called()

    def test_single_article_success(self, writer):
        writer._mock_client.put_records.return_value = {
            "FailedRecordCount": 0,
            "Records": [{"SequenceNumber": "1", "ShardId": "shard-0"}],
        }

        result = writer.write([_make_article()])
        assert result == 1
        writer._mock_client.put_records.assert_called_once()

        call_args = writer._mock_client.put_records.call_args
        records = call_args.kwargs["Records"]
        assert len(records) == 1
        assert records[0]["PartitionKey"] == "test123"

        data = json.loads(records[0]["Data"])
        assert data["title"] == "Test Title"

    def test_multiple_articles(self, writer):
        articles = [_make_article(f"id-{i}", f"https://example.com/{i}") for i in range(5)]
        writer._mock_client.put_records.return_value = {
            "FailedRecordCount": 0,
            "Records": [{"SequenceNumber": str(i), "ShardId": "shard-0"} for i in range(5)],
        }

        result = writer.write(articles)
        assert result == 5

    def test_batching_over_limit(self, writer):
        articles = [_make_article(f"id-{i}", f"https://example.com/{i}") for i in range(KINESIS_MAX_BATCH + 10)]

        def mock_put(**kwargs):
            count = len(kwargs["Records"])
            return {
                "FailedRecordCount": 0,
                "Records": [{"SequenceNumber": str(i), "ShardId": "shard-0"} for i in range(count)],
            }

        writer._mock_client.put_records.side_effect = mock_put

        result = writer.write(articles)
        assert result == KINESIS_MAX_BATCH + 10
        assert writer._mock_client.put_records.call_count == 2


class TestRetryLogic:
    def test_retries_failed_records(self, writer):
        writer._mock_client.put_records.side_effect = [
            {
                "FailedRecordCount": 1,
                "Records": [
                    {"SequenceNumber": "1", "ShardId": "shard-0"},
                    {"ErrorCode": "ProvisionedThroughputExceededException", "ErrorMessage": "slow down"},
                ],
            },
            {
                "FailedRecordCount": 0,
                "Records": [{"SequenceNumber": "2", "ShardId": "shard-0"}],
            },
        ]

        articles = [_make_article("a", "https://example.com/a"), _make_article("b", "https://example.com/b")]
        result = writer.write(articles)
        assert result == 2
        assert writer._mock_client.put_records.call_count == 2

    def test_throughput_exception_retries(self, writer):
        error_response = {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow down"}}
        writer._mock_client.put_records.side_effect = [
            ClientError(error_response, "PutRecords"),
            {
                "FailedRecordCount": 0,
                "Records": [{"SequenceNumber": "1", "ShardId": "shard-0"}],
            },
        ]

        result = writer.write([_make_article()])
        assert result == 1

    def test_non_throughput_client_error_stops(self, writer):
        error_response = {"Error": {"Code": "ResourceNotFoundException", "Message": "stream not found"}}
        writer._mock_client.put_records.side_effect = ClientError(error_response, "PutRecords")

        result = writer.write([_make_article()])
        assert result == 0
        assert writer._mock_client.put_records.call_count == 1
