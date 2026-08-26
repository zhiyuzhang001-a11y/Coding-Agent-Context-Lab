"""Frozen Alpha service settings fixture."""

SERVICE_NAME = "alpha"
HOST = "127.0.0.1"
PORT = 8142
LOG_LEVEL = "INFO"
MAX_RETRIES = 7
RETRY_BACKOFF_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 30
HEALTH_PATH = "/healthz"
METRICS_PATH = "/metrics"
FEATURE_FLAGS = {
    "audit": True,
    "metrics": True,
    "experimental_cache": False,
}
RATE_LIMITS = {
    "anonymous": 20,
    "authenticated": 100,
    "internal": 500,
}

