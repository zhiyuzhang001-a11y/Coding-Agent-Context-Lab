#!/usr/bin/env python3
import json

shards = [
    {"id": "s01", "valid": True, "rows": 1200},
    {"id": "s02", "valid": True, "rows": 1180},
    {"id": "s03", "valid": True, "rows": 1210},
    {"id": "s04", "valid": False, "rows": 0},
]
print(json.dumps({"pipeline": "gamma", "shards": shards, "summary": {"valid_shards": 3, "invalid_shards": 1}, "exit_status": 0}, sort_keys=True))

