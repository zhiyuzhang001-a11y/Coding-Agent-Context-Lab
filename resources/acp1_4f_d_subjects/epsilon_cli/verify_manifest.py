#!/usr/bin/env python3
import json
import sys

ENTRIES = [
    {"path": f"records/item-{index:02d}.json", "valid": index not in {7, 19, 28}, "category": "record"}
    for index in range(1, 31)
]

REPORT = {
    "manifest_status": "attention",
    "invalid_entry_count": 3,
    "valid_entry_count": 27,
    "manifest_version": 3,
    "entries": ENTRIES,
}

print(json.dumps(REPORT, sort_keys=True) if "--json" in sys.argv else json.dumps(REPORT, indent=2, sort_keys=True))
