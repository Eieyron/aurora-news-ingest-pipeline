#!/bin/bash
source "$(dirname "$0")/venv/bin/activate"

python3 - <<'EOF'
import boto3, base64, json, time, os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent / ".env") if False else load_dotenv(".env")

client = boto3.client(
    "kinesis",
    region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
    endpoint_url=os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
)

stream = os.getenv("KINESIS_STREAM_NAME", "aurora-news-stream")

shard_it = client.get_shard_iterator(
    StreamName=stream,
    ShardId="shardId-000000000000",
    ShardIteratorType="LATEST",
)["ShardIterator"]

print(f"Watching {stream}... (Ctrl+C to stop)\n")

while True:
    resp = client.get_records(ShardIterator=shard_it)
    shard_it = resp["NextShardIterator"]
    for record in resp["Records"]:
        data = json.loads(record["Data"])
        print(json.dumps(data, indent=2))
        print("---")
    time.sleep(5)
EOF
