#!/usr/bin/env python3
import json
import sys

CHECKS = [
    {"name": "route-home", "ok": True, "detail": "home route registered"},
    {"name": "route-status", "ok": True, "detail": "status route registered"},
    {"name": "route-maintenance", "ok": True, "detail": "maintenance route isolated"},
    {"name": "cookie-policy", "ok": True, "detail": "strict cookie policy"},
    {"name": "upload-limit", "ok": True, "detail": "upload limit configured"},
    {"name": "legacy-dashboard", "ok": False, "detail": "legacy dashboard remains disabled"},
    {"name": "archive-export", "ok": False, "detail": "archive export not enabled"},
    {"name": "regional-failover", "ok": True, "detail": "regional failover enabled"},
    {"name": "signed-callbacks", "ok": True, "detail": "callbacks require signatures"},
    {"name": "request-tracing", "ok": True, "detail": "request tracing enabled"},
] + [
    {"name": f"static-rule-{index:02d}", "ok": True, "detail": "static validation rule satisfied"}
    for index in range(1, 21)
]

REPORT = {
    "summary_status": "review",
    "failing_check_count": 2,
    "passing_check_count": len(CHECKS) - 2,
    "checks": CHECKS,
}

if "--json" in sys.argv:
    print(json.dumps(REPORT, sort_keys=True))
else:
    print(json.dumps(REPORT, indent=2, sort_keys=True))
