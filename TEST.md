# Test Results — Aurora Analytics News Ingest Pipeline

**Date:** 2026-03-13T20:56:18+0800
**Platform:** macOS (darwin 25.2.0), Python 3.13.3
**LocalStack:** v4.14.1 (Docker)

---

## Summary

| # | Check | Result |
|---|-------|--------|
| 1 | NewsAPI Connectivity | PASS |
| 2 | LocalStack Kinesis Connectivity | PASS |
| 3 | Data Processing & Validation | PASS |
| 4 | Deduplication | PASS |
| 5 | Kinesis Write & Read-Back | PASS |
| 6 | Docker Image Build | PASS |
| 7 | Unit & Integration Test Suite (36/36) | PASS |

**Overall: 7/7 checks passed**

---

## 1. NewsAPI Connectivity

Verified live connection to the NewsAPI Everything endpoint.

| Property | Value |
|----------|-------|
| Endpoint | `https://newsapi.org/v2/everything` |
| HTTP Status | `200` |
| API Status | `ok` |
| Total Results | 38,298 |
| Articles Fetched | 5 |

**Sample Article Returned:**

| Field | Value |
|-------|-------|
| Title | TCL NXTPAPER 70 Pro: lo schermo che ama i tuoi occhi è la vera rivoluzione tech? |
| Source | Everyeye.it |
| Author | Alessio Marino |
| URL | https://tech.everyeye.it/notizie/tcl-nxtpaper-70-pro-schermo-ama-occhi-vera-rivoluzione-tech-863354.html |
| PublishedAt | 2026-03-12T12:52:00Z |
| Content | Tra i numerosi annunci di TCL al Mobile World Congress 2026 di Barcellona... |

**Result: PASS**

---

## 2. LocalStack Kinesis Connectivity

Verified the local Kinesis stream is active and accepting requests.

| Property | Value |
|----------|-------|
| Endpoint | `http://localhost:4566` |
| Region | `ap-southeast-1` |
| Stream Name | `aurora-news-stream` |
| Stream Status | `ACTIVE` |
| Shard Count | 1 |
| Retention | 24 hrs |
| Stream ARN | `arn:aws:kinesis:ap-southeast-1:000000000000:stream/aurora-news-stream` |

**Result: PASS**

---

## 3. Data Processing & Validation

Fetched 5 real articles from NewsAPI and ran them through the Pydantic processing pipeline.

| Metric | Value |
|--------|-------|
| Input articles | 5 |
| Output articles | 5 |
| All 8 required fields present | Yes |

**Processed Article Sample:**

| Field | Value |
|-------|-------|
| `article_id` | `167236a84ba6b329` |
| `source_name` | `Everyeye.it` |
| `title` | TCL NXTPAPER 70 Pro: lo schermo che ama i tuoi occhi... |
| `content` | Tra i numerosi annunci di TCL al Mobile World Congress 2026... |
| `url` | https://tech.everyeye.it/notizie/tcl-nxtpaper-70-pro-... |
| `author` | Alessio Marino |
| `published_at` | `2026-03-12T12:52:00+00:00` |
| `ingested_at` | `2026-03-13T12:56:19.677300+00:00` |

**Required fields check:** `article_id`, `source_name`, `title`, `content`, `url`, `author`, `published_at`, `ingested_at` — all present.

**Result: PASS**

---

## 4. Deduplication

Verified that the URL-based deduplication cache correctly filters duplicate articles.

| Metric | Value |
|--------|-------|
| First pass (new articles) | 5 |
| Second pass (same articles, should be 0) | 0 |

**Result: PASS**

---

## 5. Kinesis Write & Read-Back

Wrote processed articles to the local Kinesis stream and read them back to verify data integrity.

| Metric | Value |
|--------|-------|
| Records written | 5/5 |
| Records read back from stream | 17 (includes records from prior test runs) |
| Schema valid on read-back | Yes |

**Last Record Read from Kinesis:**

```json
{
  "article_id": "fef1e57895af3908",
  "source_name": "HITC - Football, Gaming, Movies, TV, Music",
  "title": "Giacomo Agostini stunned that Yamaha build '20,000 bikes daily' yet struggle for...",
  "content": "Giacomo Agostini has been left puzzled by Yamahas continued difficulties in Moto...",
  "url": "https://www.hitc.com/giacomo-agostini-stunned-that-yamaha-build-20000-bikes-dail...",
  "author": "David Comerford",
  "published_at": "2026-03-12T12:49:09+00:00",
  "ingested_at": "2026-03-13T12:56:19.677357+00:00"
}
```

**Result: PASS**

---

## 6. Docker Image Build

Built the Docker image successfully using `docker build`.

| Property | Value |
|----------|-------|
| Image name | `aurora-news-ingest` |
| Base image | `python:3.12-slim` |
| Build result | SUCCESS |

**Result: PASS**

---

## 7. Unit & Integration Test Suite

Full pytest run: **36 passed, 0 failed, 0 skipped**.

### Unit Tests (31 tests)

#### `tests/test_news_client.py` — 10 tests

| # | Test | Result |
|---|------|--------|
| 1 | `test_successful_fetch` — mocked 200 response returns articles | PASS |
| 2 | `test_api_error_status` — API error response returns empty list | PASS |
| 3 | `test_empty_articles` — empty article list handled | PASS |
| 4 | `test_retry_on_timeout` — retries after request timeout | PASS |
| 5 | `test_retry_on_rate_limit` — retries on 429 status | PASS |
| 6 | `test_all_retries_exhausted` — returns empty after 3 failures | PASS |
| 7 | `test_filters_duplicates` — duplicate URLs filtered out | PASS |
| 8 | `test_skips_null_urls` — articles with null URL skipped | PASS |
| 9 | `test_remembers_across_calls` — dedup persists between calls | PASS |
| 10 | `test_evicts_oldest_when_cache_full` — cache bounded at 5000 | PASS |

#### `tests/test_processor.py` — 14 tests

| # | Test | Result |
|---|------|--------|
| 1 | `test_valid_article` — all fields populated correctly | PASS |
| 2 | `test_content_truncation_stripped` — `[+N chars]` removed | PASS |
| 3 | `test_content_none_becomes_empty` — null content → `""` | PASS |
| 4 | `test_published_at_z_suffix_normalized` — `Z` → `+00:00` | PASS |
| 5 | `test_published_at_none_becomes_empty` — null → `""` | PASS |
| 6 | `test_deterministic` — same URL → same article_id | PASS |
| 7 | `test_different_urls_different_ids` — unique URLs → unique IDs | PASS |
| 8 | `test_length` — article_id is 16 characters | PASS |
| 9 | `test_processes_valid_articles` — full processing pipeline | PASS |
| 10 | `test_null_author_defaults_to_unknown` — null → `"Unknown"` | PASS |
| 11 | `test_null_source_defaults_to_unknown` — null → `"Unknown"` | PASS |
| 12 | `test_null_title_defaults_to_untitled` — null → `"Untitled"` | PASS |
| 13 | `test_empty_list` — empty input returns empty output | PASS |
| 14 | `test_all_eight_fields_present` — schema has all 8 fields | PASS |

#### `tests/test_kinesis_writer.py` — 7 tests

| # | Test | Result |
|---|------|--------|
| 1 | `test_empty_list_returns_zero` — no records, no API call | PASS |
| 2 | `test_single_article_success` — 1 record written correctly | PASS |
| 3 | `test_multiple_articles` — batch of 5 written | PASS |
| 4 | `test_batching_over_limit` — splits at 500 records per batch | PASS |
| 5 | `test_retries_failed_records` — retries only failed records | PASS |
| 6 | `test_throughput_exception_retries` — handles throughput error | PASS |
| 7 | `test_non_throughput_client_error_stops` — non-retryable error stops | PASS |

### Integration Tests (5 tests)

| # | Test | Result |
|---|------|--------|
| 1 | `test_fetch_returns_articles` — real NewsAPI returns articles | PASS |
| 2 | `test_fetch_and_process_pipeline` — fetch + process end-to-end | PASS |
| 3 | `test_deduplication_on_real_data` — dedup works on live data | PASS |
| 4 | `test_write_and_read_records` — write to LocalStack Kinesis and verify | PASS |
| 5 | `test_full_pipeline` — NewsAPI → process → Kinesis → read-back | PASS |

---

## How to Reproduce

### Run unit tests only (no external dependencies)

```bash
source venv/bin/activate
python -m pytest tests/test_news_client.py tests/test_processor.py tests/test_kinesis_writer.py -v
```

### Run integration tests (requires LocalStack + NewsAPI key)

```bash
# Start LocalStack
docker run -d --name localstack -p 4566:4566 -e SERVICES=kinesis localstack/localstack

# Create Kinesis stream
python -c "
import boto3, time
c = boto3.client('kinesis', region_name='ap-southeast-1', endpoint_url='http://localhost:4566', aws_access_key_id='test', aws_secret_access_key='test')
c.create_stream(StreamName='aurora-news-stream', ShardCount=1)
time.sleep(2)
print('Stream created:', c.list_streams()['StreamNames'])
"

# Run all tests
python -m pytest tests/ -v
```

### Run full verification script

```bash
python run_verification.py
```
