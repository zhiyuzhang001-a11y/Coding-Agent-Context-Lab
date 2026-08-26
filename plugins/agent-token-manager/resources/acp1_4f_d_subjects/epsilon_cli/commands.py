"""Command catalog used by the epsilon development project."""

COMMANDS = [
    {"name": "archive", "category": "lifecycle", "visibility": "public", "note": "archive completed records"},
    {"name": "archive-list", "category": "lifecycle", "visibility": "public", "note": "list archive entries"},
    {"name": "archive-check", "category": "diagnostic", "visibility": "internal", "note": "verify archive consistency"},
    {"name": "archive-prune", "category": "maintenance", "visibility": "admin", "note": "prune archive entries"},
    {"name": "archive-export", "category": "reporting", "visibility": "public", "note": "export archive metadata"},
    {"name": "legacy_sync", "category": "migration", "visibility": "hidden", "note": "legacy sync remains unavailable"},
    {"name": "legacy_sync_status", "category": "diagnostic", "visibility": "internal", "note": "legacy sync status"},
    {"name": "legacy_sync_plan", "category": "migration", "visibility": "hidden", "note": "legacy sync migration plan"},
    {"name": "legacy_sync_audit", "category": "audit", "visibility": "admin", "note": "legacy sync history"},
    {"name": "legacy_sync_cleanup", "category": "maintenance", "visibility": "hidden", "note": "legacy sync cleanup"},
    {"name": "show", "category": "query", "visibility": "public", "note": "show one record"},
    {"name": "list", "category": "query", "visibility": "public", "note": "list records"},
]
