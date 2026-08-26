"""Route registry with deliberately repeated lifecycle evidence."""

ROUTES = [
    {"name": "home", "status": "active", "owner": "core", "note": "standard route"},
    {"name": "maintenance_access", "status": "staff_only", "owner": "operations", "note": "maintenance entry for controlled access"},
    {"name": "maintenance_window", "status": "scheduled", "owner": "operations", "note": "maintenance timing information"},
    {"name": "maintenance_history", "status": "read_only", "owner": "audit", "note": "maintenance event history"},
    {"name": "maintenance_preview", "status": "disabled", "owner": "design", "note": "maintenance preview experiments"},
    {"name": "maintenance_notice", "status": "active", "owner": "communications", "note": "maintenance customer notice"},
    {"name": "retired_endpoint", "status": "gone", "owner": "legacy", "note": "retired endpoint returns a stable tombstone"},
    {"name": "retired_endpoint_metrics", "status": "internal", "owner": "legacy", "note": "retired endpoint counters"},
    {"name": "retired_endpoint_docs", "status": "archived", "owner": "docs", "note": "retired endpoint migration notes"},
    {"name": "retired_endpoint_redirect", "status": "disabled", "owner": "legacy", "note": "retired endpoint redirect switch"},
    {"name": "retired_endpoint_audit", "status": "read_only", "owner": "audit", "note": "retired endpoint audit trail"},
    {"name": "status", "status": "active", "owner": "core", "note": "public health route"},
]
