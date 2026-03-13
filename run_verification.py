"""Comprehensive verification of all pipeline components."""
import json
import time
import sys
import subprocess

import boto3
import requests

from app.config import Config
from app.news_client import NewsClient
from app.processor import process_articles
from app.kinesis_writer import KinesisWriter

results = {}


def section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def test_newsapi():
    section("1. NewsAPI Connectivity")
    print(f"  Endpoint:  {Config.NEWSAPI_BASE_URL}")
    print(f"  API Key:   {Config.NEWSAPI_KEY[:4]}****")
    print(f"  Query:     {Config.NEWSAPI_QUERY}")
    print(f"  PageSize:  {Config.NEWSAPI_PAGE_SIZE}")
    print()

    resp = requests.get(
        Config.NEWSAPI_BASE_URL,
        params={"q": Config.NEWSAPI_QUERY, "pageSize": 5, "sortBy": "publishedAt"},
        headers={"X-Api-Key": Config.NEWSAPI_KEY},
        timeout=15,
    )
    data = resp.json()

    print(f"  HTTP Status:      {resp.status_code}")
    print(f"  API Status:       {data.get('status')}")
    print(f"  Total Results:    {data.get('totalResults')}")
    articles = data.get("articles", [])
    print(f"  Articles Fetched: {len(articles)}")

    if articles:
        a = articles[0]
        print()
        print("  --- Sample Article ---")
        print(f"  Title:       {(a.get('title') or '')[:80]}")
        print(f"  Source:      {(a.get('source') or {}).get('name', 'N/A')}")
        print(f"  Author:      {a.get('author', 'N/A')}")
        print(f"  URL:         {a.get('url', 'N/A')}")
        print(f"  PublishedAt: {a.get('publishedAt', 'N/A')}")
        content = (a.get("content") or "")[:100]
        print(f"  Content:     {content}...")

    ok = resp.status_code == 200 and data.get("status") == "ok" and len(articles) > 0
    results["NewsAPI Connectivity"] = "PASS" if ok else "FAIL"
    print(f"\n  RESULT: {results['NewsAPI Connectivity']}")
    return articles


def test_kinesis():
    section("2. LocalStack Kinesis Connectivity")
    print(f"  Endpoint:    {Config.AWS_ENDPOINT_URL}")
    print(f"  Region:      {Config.AWS_REGION}")
    print(f"  Stream Name: {Config.KINESIS_STREAM_NAME}")
    print()

    client = boto3.client(
        "kinesis",
        region_name=Config.AWS_REGION,
        endpoint_url=Config.AWS_ENDPOINT_URL,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    streams = client.list_streams()
    print(f"  Available Streams: {streams['StreamNames']}")

    desc = client.describe_stream(StreamName=Config.KINESIS_STREAM_NAME)
    sd = desc["StreamDescription"]
    print(f"  Stream Status:     {sd['StreamStatus']}")
    print(f"  Shard Count:       {len(sd['Shards'])}")
    print(f"  Retention:         {sd['RetentionPeriodHours']} hrs")
    print(f"  Stream ARN:        {sd['StreamARN']}")

    ok = sd["StreamStatus"] == "ACTIVE"
    results["Kinesis Connectivity"] = "PASS" if ok else "FAIL"
    print(f"\n  RESULT: {results['Kinesis Connectivity']}")
    return client, sd["Shards"][0]["ShardId"]


def test_processing(raw_articles):
    section("3. Data Processing & Validation")
    processed = process_articles(raw_articles)
    print(f"  Input articles:  {len(raw_articles)}")
    print(f"  Output articles: {len(processed)}")
    print()

    if processed:
        a = processed[0]
        data = a.model_dump()
        print("  --- Processed Article ---")
        for key, val in data.items():
            display = str(val)[:80]
            print(f"  {key:15s}: {display}")
        print()

        required = {"article_id", "source_name", "title", "content", "url", "author", "published_at", "ingested_at"}
        present = set(data.keys())
        all_present = required.issubset(present)
        print(f"  Required fields (8): {sorted(required)}")
        print(f"  All 8 fields present: {all_present}")

    ok = len(processed) > 0
    results["Data Processing"] = "PASS" if ok else "FAIL"
    print(f"\n  RESULT: {results['Data Processing']}")
    return processed


def test_deduplication(raw_articles):
    section("4. Deduplication")
    client = NewsClient()
    first_pass = client.deduplicate(raw_articles)
    second_pass = client.deduplicate(raw_articles)
    print(f"  First pass:  {len(first_pass)} new articles")
    print(f"  Second pass: {len(second_pass)} new articles (should be 0)")

    ok = len(first_pass) > 0 and len(second_pass) == 0
    results["Deduplication"] = "PASS" if ok else "FAIL"
    print(f"\n  RESULT: {results['Deduplication']}")


def test_kinesis_write(processed, kinesis_client, shard_id):
    section("5. Kinesis Write & Read-Back")
    writer = KinesisWriter()
    written = writer.write(processed)
    print(f"  Records written: {written}/{len(processed)}")

    time.sleep(1)

    iterator = kinesis_client.get_shard_iterator(
        StreamName=Config.KINESIS_STREAM_NAME,
        ShardId=shard_id,
        ShardIteratorType="TRIM_HORIZON",
    )["ShardIterator"]

    response = kinesis_client.get_records(ShardIterator=iterator, Limit=100)
    records = response["Records"]
    print(f"  Records read back: {len(records)}")
    print()

    if records:
        last = json.loads(records[-1]["Data"])
        print("  --- Last Record from Kinesis ---")
        for key, val in last.items():
            display = str(val)[:80]
            print(f"  {key:15s}: {display}")
        print()

        required = {"article_id", "source_name", "title", "content", "url", "author", "published_at", "ingested_at"}
        schema_ok = required.issubset(set(last.keys()))
        print(f"  Schema valid: {schema_ok}")

    ok = written == len(processed) and len(records) >= 1
    results["Kinesis Write/Read"] = "PASS" if ok else "FAIL"
    print(f"\n  RESULT: {results['Kinesis Write/Read']}")


def test_docker_build():
    section("6. Docker Image Build")
    result = subprocess.run(
        ["docker", "build", "-t", "aurora-news-ingest", "."],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode == 0:
        print("  Docker build: SUCCESS")
    else:
        print("  Docker build: FAILED")
        stderr = result.stderr.strip().split("\n")
        for line in stderr[-3:]:
            print(f"  {line}")

    ok = result.returncode == 0
    results["Docker Build"] = "PASS" if ok else "FAIL"
    print(f"\n  RESULT: {results['Docker Build']}")


def test_pytest():
    section("7. Unit & Integration Test Suite")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        capture_output=True, text=True, timeout=60,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr[-500:])

    ok = result.returncode == 0
    results["Test Suite"] = "PASS" if ok else "FAIL"
    print(f"\n  RESULT: {results['Test Suite']}")


if __name__ == "__main__":
    print("\n" + "#" * 60)
    print("  AURORA ANALYTICS — COMPREHENSIVE PIPELINE VERIFICATION")
    print(f"  Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    print("#" * 60)

    raw = test_newsapi()
    kinesis_client, shard_id = test_kinesis()
    processed = test_processing(raw)
    test_deduplication(raw)
    test_kinesis_write(processed, kinesis_client, shard_id)
    test_docker_build()
    test_pytest()

    section("SUMMARY")
    for name, status in results.items():
        icon = "+" if status == "PASS" else "x"
        print(f"  [{icon}] {name}: {status}")
    total = len(results)
    passed = sum(1 for v in results.values() if v == "PASS")
    print(f"\n  {passed}/{total} checks passed")
