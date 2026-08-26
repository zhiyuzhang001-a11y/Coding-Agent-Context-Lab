"""Metadata configuration for eta_library."""

LIBRARY_NAME = "eta-reference"
DEFAULT_BORROW_DAYS = 23
MAX_RENEWALS = 5
SEARCH_RESULT_LIMIT = 68
CATALOG_BATCH_SIZE = 92
OVERDUE_GRACE_DAYS = 4
ARCHIVE_AFTER_YEARS = 11
DEFAULT_LANGUAGE = "en"
ENABLE_DIGITAL_LOANS = True
ENABLE_LEGACY_IMPORT = False

COLLECTION_LIMITS = {
    "general": 18000,
    "reference": 4200,
    "periodicals": 7600,
    "digital": 25000,
    "archives": 3100,
}

POLICIES = {
    "guest": {"borrow_limit": 2, "renewals": 0},
    "member": {"borrow_limit": 12, "renewals": 5},
    "researcher": {"borrow_limit": 30, "renewals": 8},
}
