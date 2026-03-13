from unittest.mock import patch, MagicMock

import pytest
import requests

from app.news_client import NewsClient


@pytest.fixture
def client():
    with patch("app.news_client.time.sleep"):
        yield NewsClient()


def _mock_response(status_code=200, json_data=None, raise_for_status=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {"status": "ok", "articles": []}
    if raise_for_status:
        resp.raise_for_status.side_effect = raise_for_status
    return resp


SAMPLE_ARTICLES = [
    {"url": "https://example.com/1", "title": "Article 1"},
    {"url": "https://example.com/2", "title": "Article 2"},
]


class TestFetchArticles:
    def test_successful_fetch(self, client):
        resp = _mock_response(json_data={"status": "ok", "articles": SAMPLE_ARTICLES})
        client._session.get = MagicMock(return_value=resp)

        articles = client.fetch_articles()
        assert len(articles) == 2
        assert articles[0]["title"] == "Article 1"

    def test_api_error_status(self, client):
        resp = _mock_response(json_data={"status": "error", "message": "apiKeyInvalid"})
        client._session.get = MagicMock(return_value=resp)

        articles = client.fetch_articles()
        assert articles == []

    def test_empty_articles(self, client):
        resp = _mock_response(json_data={"status": "ok", "articles": []})
        client._session.get = MagicMock(return_value=resp)

        articles = client.fetch_articles()
        assert articles == []

    @patch("app.news_client.time.sleep")
    def test_retry_on_timeout(self, mock_sleep, client):
        client._session.get = MagicMock(
            side_effect=[
                requests.exceptions.Timeout("timed out"),
                _mock_response(json_data={"status": "ok", "articles": SAMPLE_ARTICLES}),
            ]
        )

        articles = client.fetch_articles()
        assert len(articles) == 2
        assert client._session.get.call_count == 2

    @patch("app.news_client.time.sleep")
    def test_retry_on_rate_limit(self, mock_sleep, client):
        rate_resp = _mock_response(status_code=429)
        ok_resp = _mock_response(json_data={"status": "ok", "articles": SAMPLE_ARTICLES})
        client._session.get = MagicMock(side_effect=[rate_resp, ok_resp])

        articles = client.fetch_articles()
        assert len(articles) == 2
        assert client._session.get.call_count == 2

    @patch("app.news_client.time.sleep")
    def test_all_retries_exhausted(self, mock_sleep, client):
        client._session.get = MagicMock(
            side_effect=requests.exceptions.ConnectionError("refused")
        )

        articles = client.fetch_articles()
        assert articles == []
        assert client._session.get.call_count == 3


class TestDeduplicate:
    def test_filters_duplicates(self, client):
        articles = [
            {"url": "https://example.com/1", "title": "A"},
            {"url": "https://example.com/2", "title": "B"},
            {"url": "https://example.com/1", "title": "A dup"},
        ]
        result = client.deduplicate(articles)
        assert len(result) == 2
        assert result[0]["title"] == "A"
        assert result[1]["title"] == "B"

    def test_skips_null_urls(self, client):
        articles = [
            {"url": None, "title": "No URL"},
            {"url": "https://example.com/1", "title": "Has URL"},
        ]
        result = client.deduplicate(articles)
        assert len(result) == 1
        assert result[0]["title"] == "Has URL"

    def test_remembers_across_calls(self, client):
        batch1 = [{"url": "https://example.com/1", "title": "First"}]
        batch2 = [
            {"url": "https://example.com/1", "title": "First again"},
            {"url": "https://example.com/2", "title": "Second"},
        ]

        result1 = client.deduplicate(batch1)
        result2 = client.deduplicate(batch2)

        assert len(result1) == 1
        assert len(result2) == 1
        assert result2[0]["title"] == "Second"

    def test_evicts_oldest_when_cache_full(self, client):
        large_batch = [{"url": f"https://example.com/{i}"} for i in range(5001)]
        client.deduplicate(large_batch)
        assert len(client._seen_urls) == 5000
