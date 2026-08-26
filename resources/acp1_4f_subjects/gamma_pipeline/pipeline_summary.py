#!/usr/bin/env python3
import json

stages = [
    {"name": "extract", "enabled": True},
    {"name": "normalize", "enabled": True},
    {"name": "deduplicate", "enabled": True},
    {"name": "partition", "enabled": True},
    {"name": "load", "enabled": True},
    {"name": "verify", "enabled": True},
]
print(json.dumps({"pipeline": "gamma", "stages": stages, "summary": {"total_stages": 6, "enabled_stages": 6}, "exit_status": 0}, sort_keys=True))

