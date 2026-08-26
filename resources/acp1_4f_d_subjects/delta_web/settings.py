"""Configuration snapshot for the delta_web development benchmark."""

SERVICE_NAME = "delta-console"
REQUEST_TIMEOUT_SECONDS = 37
CACHE_ENTRY_LIMIT = 640
SESSION_WINDOW_MINUTES = 45
MAX_UPLOAD_MEGABYTES = 18
DEFAULT_REGION = "north-2"
ENABLE_AUDIT_LOG = True
RETRY_BACKOFF_SECONDS = 6
HEALTH_SAMPLE_SIZE = 125
COOKIE_POLICY = "strict"

FEATURE_FLAGS = {
    "compact_navigation": False,
    "service_banner": True,
    "maintenance_panel": True,
    "archive_export": False,
    "request_tracing": True,
    "regional_failover": True,
    "signed_callbacks": True,
    "legacy_dashboard": False,
}

REGION_LIMITS = {
    "north-1": 420,
    "north-2": 640,
    "south-1": 510,
    "west-1": 390,
    "east-1": 475,
}
