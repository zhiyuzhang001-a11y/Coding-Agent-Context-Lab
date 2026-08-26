#!/usr/bin/env python3
import json
import sys

COLLECTIONS = [
    {"collection": f"collection-{index:02d}", "indexed": index not in {8, 17}, "items": 300 + index * 23}
    for index in range(1, 29)
]

REPORT = {
    "catalog_status": "partial",
    "unindexed_collection_count": 2,
    "indexed_collection_count": 26,
    "total_collections": 28,
    "collections": COLLECTIONS,
}

print(json.dumps(REPORT, sort_keys=True) if "--json" in sys.argv else json.dumps(REPORT, indent=2, sort_keys=True))
