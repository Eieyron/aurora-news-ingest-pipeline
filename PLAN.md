# News Ingest Pipeline — Step-by-Step Plan

## Challenge Summary

Build a Python service for **Aurora Analytics** that periodically fetches news articles from **NewsAPI.org** (Everything endpoint), processes/validates the data, and streams structured JSON records into an **AWS Kinesis Data Stream**. The application must be containerized with **Docker**.

---

## Phase 1: Project Setup

### Step 1 — Initialize the Repository
- Create project directory structure:
  ```
  manilaRecruitment/
  ├── app/
  │   ├── __init__.py
  │   ├── main.py            # Entry point / scheduler loop
  │   ├── config.py           # Configuration & env vars
  │   ├── news_client.py      # NewsAPI integration
  │   ├── processor.py        # Data processing & validation
  │   └── kinesis_writer.py   # AWS Kinesis producer
  ├── tests/
  │   ├── __init__.py
  │   ├── test_news_client.py
  │   ├── test_processor.py
  │   └── test_kinesis_writer.py
  ├── Dockerfile
  ├── docker-compose.yml
  ├── requirements.txt
  ├── .env.example
  ├── .gitignore
  ├── README.md
  └── PLAN.md
  ```
- Initialize git repo (`git init`).
- Create `.gitignore` (Python defaults, `.env`, `__pycache__`, etc.).
- Create `.env.example` with placeholder keys.

### Step 2 — Define Dependencies (`requirements.txt`)
- `requests` — HTTP client for NewsAPI calls.
- `boto3` — AWS SDK for Kinesis integration.
- `pydantic` — Data validation and schema enforcement.
- `python-dotenv` — Load environment variables from `.env`.
- `schedule` or use `asyncio` with `aiohttp` — Periodic polling / async fetching.
- `pytest` — Unit testing.

---

## Phase 2: Configuration

### Step 3 — Configuration Module (`app/config.py`)
- Load settings from environment variables (with `python-dotenv`):
  - `NEWSAPI_KEY` — API key for NewsAPI.org.
  - `NEWSAPI_BASE_URL` — Default: `https://newsapi.org/v2/everything`.
  - `KINESIS_STREAM_NAME` — Name of the target Kinesis stream.
  - `AWS_REGION` — AWS region (e.g., `ap-southeast-1`).
  - `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — AWS credentials.
  - `POLL_INTERVAL_SECONDS` — How often to fetch (e.g., `60`).
  - `NEWSAPI_QUERY` — Default search query/topic (e.g., `technology`).
  - `NEWSAPI_PAGE_SIZE` — Number of articles per request (max 100).
- Validate that all required variables are set at startup; fail fast if missing.

---

## Phase 3: API Integration (NewsAPI)

### Step 4 — NewsAPI Client (`app/news_client.py`)
- Implement `fetch_articles()` function:
  - Call `GET /v2/everything` with query params (`q`, `pageSize`, `sortBy=publishedAt`, `apiKey`).
  - Handle HTTP errors (4xx/5xx) with retries and exponential backoff.
  - Handle rate limiting (NewsAPI free tier: 100 req/day).
  - Return the raw list of article dicts from the `articles` field in the response.
- Track the latest `publishedAt` timestamp to avoid re-fetching duplicates on subsequent polls.

### Step 5 — Deduplication Strategy
- Maintain an in-memory set (or small cache) of recently seen article URLs to skip duplicates.
- Use the `url` field as a natural unique key.
- Optionally use `publishedAt` as a high-water mark to request only newer articles.

---

## Phase 4: Data Processing & Validation

### Step 6 — Data Model (`app/processor.py`)
- Define a **Pydantic** model `Article` with these fields:
  | Field          | Type     | Source / Notes                                      |
  |----------------|----------|-----------------------------------------------------|
  | `article_id`   | `str`    | Generate a UUID or hash from the article URL.       |
  | `source_name`  | `str`    | From `source.name` in API response.                 |
  | `title`        | `str`    | Direct mapping.                                     |
  | `content`      | `str`    | Direct mapping; may need truncation handling.       |
  | `url`          | `str`    | Direct mapping.                                     |
  | `author`       | `str`    | Direct mapping; default to `"Unknown"` if null.     |
  | `published_at` | `str`    | ISO 8601 from API; parse and re-format.             |
  | `ingested_at`  | `str`    | Current UTC timestamp at processing time.           |

### Step 7 — Processing Pipeline
- Implement `process_articles(raw_articles: list) -> list[Article]`:
  - Map each raw dict to the `Article` model.
  - Strip/clean HTML or trailing truncation markers (e.g., `[+1234 chars]`).
  - Validate with Pydantic; log and skip invalid records.
  - Return list of validated `Article` objects.

---

## Phase 5: AWS Kinesis Integration

### Step 8 — Kinesis Writer (`app/kinesis_writer.py`)
- Initialize a `boto3` Kinesis client using configured credentials and region.
- Implement `write_to_kinesis(articles: list[Article])`:
  - Serialize each `Article` to JSON.
  - Use `put_records()` (batch API) for efficiency — batch up to 500 records per call.
  - Use `article_id` as the **partition key** for even shard distribution.
  - Handle `ProvisionedThroughputExceededException` with retry + backoff.
  - Log success/failure counts.

### Step 9 — Kinesis Stream Setup (AWS side)
- Document in README how to create the stream:
  ```bash
  aws kinesis create-stream --stream-name aurora-news-stream --shard-count 1
  ```
- Alternatively, provide a small setup script or note about using **LocalStack** for local development/testing.

---

## Phase 6: Main Application Loop

### Step 10 — Orchestrator (`app/main.py`)
- On startup:
  1. Load config, validate.
  2. Log startup banner with settings (mask secrets).
- Enter polling loop:
  1. Call `fetch_articles()`.
  2. Deduplicate against recently seen.
  3. Call `process_articles()` on new articles.
  4. Call `write_to_kinesis()` with processed batch.
  5. Log summary (articles fetched, processed, written).
  6. Sleep for `POLL_INTERVAL_SECONDS`.
- Handle graceful shutdown on `SIGINT` / `SIGTERM`.
- Wrap each cycle in try/except to ensure the loop continues on transient errors.

---

## Phase 7: Containerization

### Step 11 — Dockerfile
- Use `python:3.12-slim` as base image.
- Copy `requirements.txt`, run `pip install`.
- Copy application code.
- Set `PYTHONUNBUFFERED=1` for real-time log output.
- Define `CMD ["python", "-m", "app.main"]`.

### Step 12 — Docker Compose (optional but useful)
- Define service for the ingest app.
- Optionally add a **LocalStack** service for local Kinesis emulation.
- Pass environment variables via `.env` file.
- Example:
  ```yaml
  services:
    ingest:
      build: .
      env_file: .env
      depends_on:
        - localstack
    localstack:
      image: localstack/localstack
      ports:
        - "4566:4566"
      environment:
        - SERVICES=kinesis
  ```

---

## Phase 8: Testing

### Step 13 — Unit Tests
- **`test_news_client.py`** — Mock HTTP responses; verify parsing, error handling, retry logic.
- **`test_processor.py`** — Test validation, cleaning, edge cases (null author, missing content).
- **`test_kinesis_writer.py`** — Mock boto3 client; verify batch formation, partition key usage, error handling.

### Step 14 — Integration / Smoke Test
- Use LocalStack to spin up a real Kinesis stream locally.
- Run the app for one cycle and verify records land in the stream.
- Read back records with `get-records` and validate JSON schema.

---

## Phase 9: Documentation

### Step 15 — README.md
- **Project overview** — What it does, architecture diagram (text-based).
- **Prerequisites** — Python 3.12+, Docker, AWS credentials, NewsAPI key.
- **Quick start** — Step-by-step to run locally and with Docker.
- **Configuration** — Table of all env vars with descriptions and defaults.
- **Architecture decisions** — Why Pydantic, polling strategy, batch writes, etc.
- **Testing** — How to run tests.
- **Improvements / Future work** — Ideas like async I/O, dead-letter queue, metrics, etc.

---

## Phase 10: Polish & Submit

### Step 16 — Code Quality
- Add type hints throughout.
- Add structured logging (use `logging` module with JSON formatter).
- Ensure no secrets are committed (`.gitignore`, `.env.example`).
- Run a linter (`ruff` or `flake8`) and fix issues.

### Step 17 — Final Review Checklist
- [ ] NewsAPI Everything endpoint integration works.
- [ ] Articles are validated and cleaned with all 8 required fields.
- [ ] Records are written to Kinesis in batches.
- [ ] Polling loop runs on a configurable interval.
- [ ] Deduplication prevents re-processing the same articles.
- [ ] Dockerfile builds and runs successfully.
- [ ] README is clear and complete.
- [ ] No secrets in the repo.
- [ ] Tests pass.
- [ ] Git history is clean with meaningful commits.

---

## Execution Order (Recommended)

| Order | Step(s)  | Description                          | Est. Time |
|-------|----------|--------------------------------------|-----------|
| 1     | 1–2      | Project scaffolding & dependencies   | 15 min    |
| 2     | 3        | Configuration module                 | 15 min    |
| 3     | 4–5      | NewsAPI client + deduplication       | 45 min    |
| 4     | 6–7      | Data model & processing pipeline     | 30 min    |
| 5     | 8–9      | Kinesis writer + stream setup        | 45 min    |
| 6     | 10       | Main loop orchestrator               | 30 min    |
| 7     | 11–12    | Docker + Compose                     | 30 min    |
| 8     | 13–14    | Tests                                | 45 min    |
| 9     | 15       | README documentation                 | 20 min    |
| 10    | 16–17    | Polish & final review                | 15 min    |
|       |          | **Total estimated time**             | **~5 hrs**|
