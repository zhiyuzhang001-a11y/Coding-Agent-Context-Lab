"""Pipeline steps and operational states."""

STEPS = [
    {"name": "load_customers", "stage": "ingest", "production_state": "enabled", "owner": "identity"},
    {"name": "load_orders", "stage": "ingest", "production_state": "enabled", "owner": "commerce"},
    {"name": "load_inventory", "stage": "ingest", "production_state": "enabled", "owner": "supply"},
    {"name": "retention_cleanup", "stage": "maintenance", "production_state": "scheduled", "owner": "platform"},
    {"name": "retention_preview", "stage": "maintenance", "production_state": "disabled", "owner": "platform"},
    {"name": "retention_audit", "stage": "audit", "production_state": "enabled", "owner": "governance"},
    {"name": "retention_metrics", "stage": "report", "production_state": "enabled", "owner": "observability"},
    {"name": "retention_backfill", "stage": "maintenance", "production_state": "manual", "owner": "platform"},
    {"name": "quarantine_router", "stage": "quality", "production_state": "enabled", "owner": "data-quality"},
    {"name": "quarantine_replay", "stage": "quality", "production_state": "manual", "owner": "data-quality"},
    {"name": "quarantine_report", "stage": "report", "production_state": "enabled", "owner": "governance"},
    {"name": "quarantine_purge", "stage": "maintenance", "production_state": "disabled", "owner": "platform"},
    {"name": "publish_summary", "stage": "publish", "production_state": "enabled", "owner": "analytics"},
]
