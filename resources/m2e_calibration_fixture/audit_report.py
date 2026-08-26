"""Small edit fixture used only to calibrate the M2e execution harness."""

from __future__ import annotations

from typing import Any


def summarize_audit(records: list[dict[str, Any]]) -> dict[str, float | int]:
    """Return basic read-volume metrics for tool-output audit records."""
    read_count = sum(bool(record.get("read_like")) for record in records)
    return {
        "tool_calls": len(records),
        "read_calls": read_count,
        "read_share_percent": round(read_count / len(records) * 100, 1),
    }
