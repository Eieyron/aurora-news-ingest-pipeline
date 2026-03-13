# Aurora Analytics — News Ingest Pipeline

A Python service that periodically fetches news articles from [NewsAPI.org](https://newsapi.org/) and streams structured records into an AWS Kinesis Data Stream for downstream processing.

## Architecture

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   NewsAPI    │─────▶│  NewsClient  │─────▶│  Processor   │─────▶│ KinesisWriter│
│  (External)  │ HTTP │  fetch +     │      │  validate +  │      │  batch write │
│              │      │  deduplicate │      │  clean       │      │  + retry     │
└──────────────┘      └──────────────┘      └──────────────┘      └──────┬───────┘
                                                                         │
                                                                         ▼
                                                                  ┌──────────────┐
                                                                  │ AWS Kinesis   │
                                                                  │ Data Stream   │
                                                                  └──────────────┘
```

The main loop polls NewsAPI on a configurable interval, deduplicates articles by URL, validates and cleans each record with Pydantic, then writes batches to Kinesis with automatic retry on failures.

## Prerequisites

- Python 3.12+
- Docker & Docker Compose (for containerized/local runs)
- A [NewsAPI](https://newsapi.org/register) API key
- AWS credentials with Kinesis `PutRecords` permission (or use LocalStack for local dev)

## Quick Start

### 1. Clone and install

```bash
git clone <repo-url>
cd manilaRecruitment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your actual keys:

```
NEWSAPI_KEY=your_real_api_key
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
```

### 3. Run locally

```bash
python -m app.main
```

### 4. Run with Docker (using LocalStack)

This spins up LocalStack for a local Kinesis stream, creates the stream, then starts the ingest service:

```bash
docker compose up --build
```

To stop:

```bash
docker compose down
```

## Configuration

All settings are loaded from environment variables (or `.env` file).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEWSAPI_KEY` | Yes | — | API key from newsapi.org |
| `NEWSAPI_BASE_URL` | No | `https://newsapi.org/v2/everything` | NewsAPI endpoint |
| `NEWSAPI_QUERY` | No | `technology` | Search query/topic |
| `NEWSAPI_PAGE_SIZE` | No | `50` | Articles per request (max 100) |
| `AWS_REGION` | No | `ap-southeast-1` | AWS region |
| `AWS_ACCESS_KEY_ID` | Yes | — | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Yes | — | AWS secret key |
| `AWS_ENDPOINT_URL` | No | — | Custom endpoint (for LocalStack) |
| `KINESIS_STREAM_NAME` | Yes | `aurora-news-stream` | Target Kinesis stream |
| `POLL_INTERVAL_SECONDS` | No | `60` | Seconds between poll cycles |

## Kinesis Record Schema

Each record written to Kinesis is a JSON object with these fields:

```json
{
  "article_id": "08ec155ece75dd96",
  "source_name": "BBC News",
  "title": "AI Breakthroughs in 2026",
  "content": "Artificial intelligence has seen major advances...",
  "url": "https://bbc.co.uk/news/tech-123",
  "author": "Jane Doe",
  "published_at": "2026-03-13T10:30:00+00:00",
  "ingested_at": "2026-03-13T11:00:05.123456+00:00"
}
```

## Project Structure

```
├── app/
│   ├── __init__.py
│   ├── main.py              # Entry point and polling loop
│   ├── config.py            # Environment configuration
│   ├── news_client.py       # NewsAPI integration + deduplication
│   ├── processor.py         # Data validation and cleaning (Pydantic)
│   └── kinesis_writer.py    # AWS Kinesis batch writer
├── tests/
│   ├── test_news_client.py
│   ├── test_processor.py
│   └── test_kinesis_writer.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## Testing

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

## Design Decisions

- **Pydantic** for data validation — enforces the output schema at the model level, catches bad data before it reaches Kinesis.
- **URL-based deduplication** — uses a bounded `OrderedDict` (FIFO eviction at 5,000 entries) to prevent re-processing the same articles across poll cycles without unbounded memory growth.
- **Batch writes** — uses Kinesis `put_records()` (up to 500 per call) for throughput efficiency instead of individual `put_record()` calls.
- **Exponential backoff** — retry logic on both the NewsAPI client and Kinesis writer handles rate limits and transient failures gracefully.
- **Graceful shutdown** — catches `SIGINT`/`SIGTERM` and finishes the current cycle before exiting, important for clean Docker container stops.
- **LocalStack in Compose** — enables local end-to-end testing without AWS costs or credentials.

## Future Improvements

- **Async I/O** — switch to `aiohttp` + `aiobotocore` for non-blocking fetch and write operations.
- **Dead-letter queue** — route persistently failing records to an SQS DLQ for manual review.
- **Metrics & monitoring** — emit CloudWatch metrics (articles/sec, error rate, latency).
- **Pagination** — fetch multiple pages per cycle for higher volume ingestion.
- **Persistent dedup store** — replace in-memory cache with Redis for deduplication across restarts.
- **Schema registry** — integrate with AWS Glue Schema Registry for downstream contract enforcement.
