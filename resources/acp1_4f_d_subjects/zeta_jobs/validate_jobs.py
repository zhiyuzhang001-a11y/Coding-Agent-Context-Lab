#!/usr/bin/env python3
import json
import sys

SHARDS = [
    {"shard": f"central-{index:02d}", "valid": index not in {5, 14, 22, 31}, "records": 1000 + index * 17}
    for index in range(1, 35)
]

REPORT = {
    "pipeline_status": "quarantine",
    "invalid_shard_count": 4,
    "valid_shard_count": 30,
    "total_shards": 34,
    "shards": SHARDS,
}

print(json.dumps(REPORT, sort_keys=True) if "--json" in sys.argv else json.dumps(REPORT, indent=2, sort_keys=True))
