"""Frozen Alpha service route table fixture."""

ROUTES = [
    {"name": "health", "path": "/healthz", "method": "GET", "status": "public"},
    {"name": "metrics", "path": "/metrics", "method": "GET", "status": "internal"},
    {"name": "maintenance", "path": "/admin/maintenance", "method": "POST", "status": "restricted"},
    {"name": "users", "path": "/v1/users", "method": "GET", "status": "authenticated"},
    {"name": "jobs", "path": "/v1/jobs", "method": "POST", "status": "authenticated"},
]


def route_names() -> list[str]:
    return [row["name"] for row in ROUTES]

