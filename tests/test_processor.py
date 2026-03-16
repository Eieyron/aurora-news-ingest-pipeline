from app.processor import Article, process_articles, _generate_article_id


class TestArticleModel:
    def test_valid_article(self):
        a = Article(
            article_id="abc123",
            source_name="BBC",
            title="Test Title",
            content="Some body text",
            url="https://example.com",
            author="Jane Doe",
            published_at="2026-03-13T10:00:00+00:00",
        )
        assert a.article_id == "abc123"
        assert a.source_name == "BBC"
        assert a.ingested_at  # auto-populated

    def test_content_truncation_stripped(self):
        a = Article(
            article_id="x",
            source_name="S",
            title="T",
            content="Article text here [+3420 chars]",
            url="https://example.com",
            author="A",
            published_at="",
        )
        assert a.content == "Article text here"

    def test_content_none_becomes_empty(self):
        a = Article(
            article_id="x",
            source_name="S",
            title="T",
            content=None,
            url="https://example.com",
            author="A",
            published_at="",
        )
        assert a.content == ""

    def test_published_at_z_suffix_normalized(self):
        a = Article(
            article_id="x",
            source_name="S",
            title="T",
            content="",
            url="https://example.com",
            author="A",
            published_at="2026-03-13T10:30:00Z",
        )
        assert "+00:00" in a.published_at
        assert "Z" not in a.published_at

    def test_published_at_none_becomes_empty(self):
        a = Article(
            article_id="x",
            source_name="S",
            title="T",
            content="",
            url="https://example.com",
            author="A",
            published_at=None,
        )
        assert a.published_at == ""


class TestGenerateArticleId:
    def test_deterministic(self):
        id1 = _generate_article_id("https://example.com/article")
        id2 = _generate_article_id("https://example.com/article")
        assert id1 == id2

    def test_different_urls_different_ids(self):
        id1 = _generate_article_id("https://example.com/1")
        id2 = _generate_article_id("https://example.com/2")
        assert id1 != id2

    def test_length(self):
        aid = _generate_article_id("https://example.com")
        assert len(aid) == 16


class TestProcessArticles:
    def test_processes_valid_articles(self):
        raw = [
            {
                "source": {"id": "bbc", "name": "BBC News"},
                "author": "Jane Doe",
                "title": "Test Article",
                "content": "Body content",
                "url": "https://example.com/1",
                "publishedAt": "2026-03-13T10:00:00Z",
            }
        ]
        result = process_articles(raw)
        assert len(result) == 1
        assert result[0].source_name == "BBC News"
        assert result[0].author == "Jane Doe"

    def test_null_author_defaults_to_unknown(self):
        raw = [
            {
                "source": {"name": "Src"},
                "author": None,
                "title": "T",
                "content": "C",
                "url": "https://example.com/1",
                "publishedAt": "",
            }
        ]
        result = process_articles(raw)
        assert result[0].author == "Unknown"

    def test_null_source_defaults_to_unknown(self):
        raw = [
            {
                "source": None,
                "author": "A",
                "title": "T",
                "content": "C",
                "url": "https://example.com/1",
                "publishedAt": "",
            }
        ]
        result = process_articles(raw)
        assert result[0].source_name == "Unknown"

    def test_null_title_defaults_to_untitled(self):
        raw = [
            {
                "source": {"name": "S"},
                "author": "A",
                "title": None,
                "content": "C",
                "url": "https://example.com/1",
                "publishedAt": "",
            }
        ]
        result = process_articles(raw)
        assert result[0].title == "Untitled"

    def test_empty_list(self):
        assert process_articles([]) == []

    def test_all_eight_fields_present(self):
        raw = [
            {
                "source": {"name": "S"},
                "author": "A",
                "title": "T",
                "content": "C",
                "url": "https://example.com/1",
                "publishedAt": "2026-01-01T00:00:00Z",
            }
        ]
        result = process_articles(raw)
        data = result[0].model_dump()
        expected_keys = {
            "article_id", "source_name", "title", "content",
            "url", "author", "published_at", "ingested_at",
        }
        assert set(data.keys()) == expected_keys
