"""Integration tests that run against real NewsAPI and local Kinesis (LocalStack).

Prerequisites:
  - LocalStack running on localhost:4566 with Kinesis
  - NEWSAPI_KEY set in .env with a valid key
  - Stream 'aurora-news-stream' created in LocalStack

Run:
  pytest tests/test_integration.py -v -s
"""

import json
import time

import boto3
import pytest
import requests

from app.config import Config
from app.kinesis_writer import KinesisWriter
from app.news_client import NewsClient
from app.processor import process_articles


def _localstack_available() -> bool:
    try:
        resp = requests.get("http://localhost:4566/_localstack/health", timeout=2)
        return resp.status_code == 200
    except requests.ConnectionError:
        return False


def _newsapi_key_valid() -> bool:
    key = Config.NEWSAPI_KEY
    return bool(key) and not key.startswith("your_") and key != "placeholder"


skip_no_localstack = pytest.mark.skipif(
    not _localstack_available(), reason="LocalStack not running on localhost:4566"
)
skip_no_newsapi = pytest.mark.skipif(
    not _newsapi_key_valid(), reason="NEWSAPI_KEY not set or invalid"
)


@skip_no_newsapi
class TestNewsAPIIntegration:
    """Tests that hit the real NewsAPI endpoint."""

    def test_fetch_returns_articles(self):
        client = NewsClient()
        articles = client.fetch_articles()

        assert isinstance(articles, list)
        assert len(articles) > 0, "Expected at least 1 article from NewsAPI"

        first = articles[0]
        assert "title" in first
        assert "url" in first
        assert "source" in first
        assert "publishedAt" in first

    def test_fetch_and_process_pipeline(self):
        client = NewsClient()
        raw = client.fetch_articles()
        assert len(raw) > 0

        processed = process_articles(raw)
        assert len(processed) > 0

        a = processed[0]
        assert a.article_id
        assert a.source_name
        assert a.title
        assert a.url
        assert a.ingested_at

    def test_deduplication_on_real_data(self):
        client = NewsClient()
        articles = client.fetch_articles()
        assert len(articles) > 0

        first_pass = client.deduplicate(articles)
        second_pass = client.deduplicate(articles)

        assert len(first_pass) > 0
        assert len(second_pass) == 0, "All articles should be filtered as duplicates"


@skip_no_localstack
class TestKinesisIntegration:
    """Tests that write and read from LocalStack Kinesis."""

    @pytest.fixture
    def kinesis_client(self):
        return boto3.client(
            "kinesis",
            region_name=Config.AWS_REGION,
            endpoint_url="http://localhost:4566",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )

    def test_write_and_read_records(self, kinesis_client):
        writer = KinesisWriter()

        raw = [
            {
                "source": {"name": "IntegrationTest"},
                "author": "Test Author",
                "title": "Integration Test Article",
                "content": "This is a test article for integration testing",
                "url": "https://integration-test.example.com/1",
                "publishedAt": "2026-03-13T00:00:00Z",
            }
        ]
        processed = process_articles(raw)
        written = writer.write(processed)

        assert written == 1

        shard_id = kinesis_client.describe_stream(
            StreamName=Config.KINESIS_STREAM_NAME
        )["StreamDescription"]["Shards"][0]["ShardId"]

        iterator = kinesis_client.get_shard_iterator(
            StreamName=Config.KINESIS_STREAM_NAME,
            ShardId=shard_id,
            ShardIteratorType="TRIM_HORIZON",
        )["ShardIterator"]

        time.sleep(1)

        response = kinesis_client.get_records(ShardIterator=iterator, Limit=100)
        records = response["Records"]

        assert len(records) >= 1

        found = False
        for record in records:
            data = json.loads(record["Data"])
            if data.get("title") == "Integration Test Article":
                assert data["source_name"] == "IntegrationTest"
                assert data["author"] == "Test Author"
                assert "article_id" in data
                assert "ingested_at" in data
                found = True
                break

        assert found, "Integration Test Article not found in Kinesis records"


@skip_no_newsapi
@skip_no_localstack
class TestEndToEnd:
    """Full pipeline: fetch from NewsAPI -> process -> write to Kinesis -> read back."""

    def test_full_pipeline(self):
        news_client = NewsClient()
        writer = KinesisWriter()
        kinesis_raw = boto3.client(
            "kinesis",
            region_name=Config.AWS_REGION,
            endpoint_url="http://localhost:4566",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )

        raw_articles = news_client.fetch_articles()
        assert len(raw_articles) > 0, "NewsAPI returned no articles"

        new_articles = news_client.deduplicate(raw_articles)
        assert len(new_articles) > 0

        processed = process_articles(new_articles)
        assert len(processed) > 0

        written = writer.write(processed)
        assert written == len(processed)

        time.sleep(1)

        shard_id = kinesis_raw.describe_stream(
            StreamName=Config.KINESIS_STREAM_NAME
        )["StreamDescription"]["Shards"][0]["ShardId"]

        iterator = kinesis_raw.get_shard_iterator(
            StreamName=Config.KINESIS_STREAM_NAME,
            ShardId=shard_id,
            ShardIteratorType="TRIM_HORIZON",
        )["ShardIterator"]

        response = kinesis_raw.get_records(ShardIterator=iterator, Limit=100)
        records = response["Records"]

        assert len(records) >= 1

        data = json.loads(records[0]["Data"])
        required_fields = {
            "article_id", "source_name", "title", "content",
            "url", "author", "published_at", "ingested_at",
        }
        assert required_fields.issubset(set(data.keys()))
