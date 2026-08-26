"""Catalog handlers with repeated lifecycle terms."""

HANDLERS = [
    {"name": "rare_collection", "access": "supervised", "state": "active", "owner": "archives"},
    {"name": "rare_collection_search", "access": "staff", "state": "active", "owner": "catalog"},
    {"name": "rare_collection_export", "access": "restricted", "state": "disabled", "owner": "archives"},
    {"name": "rare_collection_audit", "access": "staff", "state": "read_only", "owner": "governance"},
    {"name": "rare_collection_preview", "access": "member", "state": "beta", "owner": "experience"},
    {"name": "legacy_import", "access": "admin", "state": "disabled", "owner": "migration"},
    {"name": "legacy_import_plan", "access": "staff", "state": "archived", "owner": "migration"},
    {"name": "legacy_import_audit", "access": "staff", "state": "read_only", "owner": "governance"},
    {"name": "legacy_import_preview", "access": "admin", "state": "disabled", "owner": "migration"},
    {"name": "legacy_import_cleanup", "access": "admin", "state": "manual", "owner": "platform"},
    {"name": "member_lookup", "access": "staff", "state": "active", "owner": "circulation"},
    {"name": "loan_history", "access": "staff", "state": "active", "owner": "circulation"},
]
