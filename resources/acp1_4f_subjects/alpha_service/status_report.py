#!/usr/bin/env python3
import json

checks = [
    {"name": "database", "status": "pass", "duration_ms": 8},
    {"name": "cache", "status": "pass", "duration_ms": 3},
    {"name": "queue", "status": "fail", "duration_ms": 21},
    {"name": "storage", "status": "pass", "duration_ms": 13},
    {"name": "mailer", "status": "pass", "duration_ms": 5},
]
print(json.dumps({"service": "alpha", "checks": checks, "summary": {"passed": 4, "failed": 1}, "exit_status": 0}, sort_keys=True))

