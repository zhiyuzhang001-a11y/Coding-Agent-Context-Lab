from __future__ import annotations

import unittest

from audit_report import summarize_audit


class AuditReportTests(unittest.TestCase):
    def test_empty_audit_has_zero_read_share(self) -> None:
        self.assertEqual(
            summarize_audit([]),
            {"tool_calls": 0, "read_calls": 0, "read_share_percent": 0.0},
        )

    def test_non_empty_audit_preserves_read_share(self) -> None:
        self.assertEqual(
            summarize_audit([{"read_like": True}, {"read_like": False}]),
            {"tool_calls": 2, "read_calls": 1, "read_share_percent": 50.0},
        )


if __name__ == "__main__":
    unittest.main()
