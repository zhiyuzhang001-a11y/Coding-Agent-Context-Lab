from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


import sys

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

from compact_navigator import CompactNavigator


class CompactNavigatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "repo"
        self.data = base / "data"
        self.root.mkdir()
        (self.root / "login_flow.py").write_text(
            "def process_login_request(session):\n"
            "    return reject_expired_credentials(session)\n\n"
            "def reject_expired_credentials(session):\n"
            "    secret = 'COMPACT SECRET BODY'\n"
            "    return session.expires_at > 0\n",
            encoding="utf-8",
        )
        (self.root / "opaque.py").write_text(
            "def alpha(data):\n"
            "    return beta(data)\n\n"
            "def beta(data):\n"
            "    return data.value\n",
            encoding="utf-8",
        )
        (self.root / "routing.py").write_text(
            "def route_invoice_event(event):\n"
            "    return persist_invoice(event)\n\n"
            "def persist_invoice(event):\n"
            "    return event.invoice_id\n",
            encoding="utf-8",
        )
        self.compact = CompactNavigator(self.root, self.data)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_direct_completion_is_one_call_budgeted_and_private(self) -> None:
        result = self.compact.navigate(
            "inspect reject_expired_credentials",
            "direct-1",
            total_budget=1800,
            navigation_budget=500,
            expansion_budget=1200,
            model_visible_budget=900,
            max_steps=3,
            max_source_reads=3,
        )
        state = self.compact.navigator.store.load(result["task_id"])
        self.assertEqual(result["phase"], "completed")
        self.assertEqual(result["stop_reason"], "evidence_sufficient")
        self.assertEqual(state.external_call_count, 1)
        self.assertLessEqual(state.consumed_tokens, state.total_budget)
        self.assertLessEqual(result["budget"]["model_visible_tokens"], 900)
        self.assertTrue(result["evidence"])
        self.assertNotIn("ranking", result)
        self.assertNotIn(b"COMPACT SECRET BODY", self.compact.navigator.provider.workspace.database.read_bytes())
        for path in self.data.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"COMPACT SECRET BODY", path.read_bytes())

    def test_fixed_third_fixture_obeys_source_read_limit(self) -> None:
        result = self.compact.navigate(
            "find where invoice events are persisted",
            "third-fixture",
            total_budget=1500,
            navigation_budget=500,
            expansion_budget=900,
            model_visible_budget=800,
            max_steps=1,
            max_source_reads=1,
        )
        state = self.compact.navigator.store.load(result["task_id"])
        self.assertLessEqual(len(state.expanded), 1)
        self.assertTrue(all(hop <= 2 for hop in state.compact_marker_hops.values()))
        self.assertLessEqual(state.consumed_tokens, state.total_budget)
        self.assertLessEqual(result["budget"]["model_visible_tokens"], 800)
        self.assertIn(result["phase"], {"completed", "needs_verification"})

    def test_too_small_model_visible_budget_is_rejected_before_navigation(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 256"):
            self.compact.navigate(
                "find invoice persistence",
                "tiny-visible-budget",
                model_visible_budget=255,
            )

    def test_navigate_request_is_idempotent_without_new_budget(self) -> None:
        first = self.compact.navigate(
            "inspect reject_expired_credentials",
            "retry-1",
            total_budget=1800,
            navigation_budget=500,
            expansion_budget=1200,
            model_visible_budget=900,
        )
        state_before = self.compact.navigator.store.load(first["task_id"])
        with mock.patch.object(
            self.compact.navigator.provider,
            "index",
            side_effect=AssertionError("idempotent replay must not re-index"),
        ):
            replay = self.compact.navigate(
                "inspect reject_expired_credentials",
                "retry-1",
                total_budget=1800,
                navigation_budget=500,
                expansion_budget=1200,
                model_visible_budget=900,
            )
        state_after = self.compact.navigator.store.load(first["task_id"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(state_after.external_call_count, 1)
        self.assertEqual(state_after.consumed_tokens, state_before.consumed_tokens)
        self.assertEqual(
            [item["hash"] for item in replay["evidence"]],
            [item["hash"] for item in first["evidence"]],
        )
        conflict = self.compact.navigate(
            "a different task must not reuse the same request id",
            "retry-1",
            total_budget=1800,
            navigation_budget=500,
            expansion_budget=1200,
            model_visible_budget=900,
        )
        self.assertEqual(conflict["error"], "invalid_feedback")

    def test_second_call_accepts_batch_feedback_and_forces_terminal_state(self) -> None:
        first = self.compact.navigate(
            "investigate mysterious behavior",
            "verify-start",
            total_budget=1800,
            navigation_budget=600,
            expansion_budget=1100,
            model_visible_budget=900,
            max_steps=1,
            max_source_reads=1,
        )
        self.assertEqual(first["phase"], "needs_verification")
        evidence_id = first["evidence"][0]["evidence_id"]
        evidence_ref = f"{evidence_id}={first['evidence'][0]['hash']}"
        final = self.compact.verify(
            first["task_id"],
            "verify-finish",
            accepted_evidence=[evidence_ref],
        )
        state = self.compact.navigator.store.load(first["task_id"])
        self.assertEqual(final["phase"], "completed")
        self.assertEqual(final["stop_reason"], "evidence_sufficient")
        self.assertEqual(state.external_call_count, 2)
        self.assertTrue(state.verification_used)

        first_replay = self.compact.navigate(
            "investigate mysterious behavior",
            "verify-start",
            total_budget=1800,
            navigation_budget=600,
            expansion_budget=1100,
            model_visible_budget=900,
            max_steps=1,
            max_source_reads=1,
        )
        self.assertTrue(first_replay["idempotent_replay"])
        self.assertEqual(first_replay["phase"], "needs_verification")
        self.assertIsNone(first_replay["stop_reason"])

        replay = self.compact.verify(
            first["task_id"],
            "verify-finish",
            accepted_evidence=[evidence_ref],
        )
        self.assertTrue(replay["idempotent_replay"])
        third = self.compact.verify(first["task_id"], "third-call")
        self.assertEqual(third["status"], "protocol_error")
        self.assertEqual(third["error"], "external_call_limit_reached")
        self.assertEqual(third["stop_reason"], "evidence_sufficient")

    def test_invalid_feedback_does_not_consume_second_call(self) -> None:
        first = self.compact.navigate(
            "investigate mysterious behavior",
            "invalid-start",
            total_budget=1800,
            navigation_budget=600,
            expansion_budget=1100,
            model_visible_budget=900,
            max_steps=1,
            max_source_reads=1,
        )
        evidence_id = first["evidence"][0]["evidence_id"]
        evidence_ref = f"{evidence_id}={first['evidence'][0]['hash']}"
        invalid = self.compact.verify(
            first["task_id"],
            "invalid-finish",
            accepted_evidence=[evidence_ref],
            rejected_evidence=[evidence_ref],
        )
        state = self.compact.navigator.store.load(first["task_id"])
        self.assertEqual(invalid["error"], "invalid_feedback")
        self.assertEqual(state.external_call_count, 1)
        self.assertFalse(state.verification_used)

    def test_second_call_without_accepted_evidence_is_inconclusive(self) -> None:
        first = self.compact.navigate(
            "investigate mysterious behavior",
            "inconclusive-start",
            total_budget=1800,
            navigation_budget=600,
            expansion_budget=1100,
            model_visible_budget=900,
            max_steps=1,
            max_source_reads=1,
        )
        evidence_id = first["evidence"][0]["evidence_id"]
        evidence_ref = f"{evidence_id}={first['evidence'][0]['hash']}"
        final = self.compact.verify(
            first["task_id"],
            "inconclusive-finish",
            uncertain_evidence=[evidence_ref],
            missing_questions=["Does this evidence implement the requested behavior?"],
        )
        self.assertEqual(final["phase"], "completed")
        self.assertEqual(final["stop_reason"], "verification_inconclusive")

    def test_second_call_can_use_one_reserved_supplemental_read(self) -> None:
        first = self.compact.navigate(
            "investigate mysterious behavior",
            "supplement-start",
            total_budget=2400,
            navigation_budget=700,
            expansion_budget=1600,
            model_visible_budget=1100,
            max_steps=2,
            max_source_reads=2,
        )
        self.assertEqual(first["phase"], "needs_verification")
        evidence = first["evidence"][0]
        final = self.compact.verify(
            first["task_id"],
            "supplement-finish",
            uncertain_evidence=[f"{evidence['evidence_id']}={evidence['hash']}"],
            missing_questions=["Which neighboring implementation resolves the behavior?"],
        )
        state = self.compact.navigator.store.load(first["task_id"])
        self.assertEqual(final["phase"], "completed")
        self.assertLessEqual(len(state.expanded), 2)
        self.assertGreaterEqual(len(state.expanded), 2)
        self.assertLessEqual(state.consumed_tokens, state.total_budget)

    def test_stale_evidence_does_not_consume_second_call(self) -> None:
        first = self.compact.navigate(
            "investigate mysterious behavior",
            "stale-start",
            total_budget=1800,
            navigation_budget=600,
            expansion_budget=1100,
            model_visible_budget=900,
            max_steps=1,
            max_source_reads=1,
        )
        evidence = first["evidence"][0]
        evidence_ref = f"{evidence['evidence_id']}={evidence['hash']}"
        (self.root / evidence["path"]).write_text(
            "def changed():\n    return True\n",
            encoding="utf-8",
        )
        stale = self.compact.verify(
            first["task_id"],
            "stale-finish",
            accepted_evidence=[evidence_ref],
        )
        state = self.compact.navigator.store.load(first["task_id"])
        self.assertEqual(stale["error"], "stale_evidence")
        self.assertEqual(state.external_call_count, 1)
        self.assertFalse(state.verification_used)

    def test_verify_after_direct_completion_is_invalid_phase(self) -> None:
        first = self.compact.navigate(
            "inspect reject_expired_credentials",
            "completed-start",
            total_budget=1800,
            navigation_budget=500,
            expansion_budget=1200,
            model_visible_budget=900,
        )
        invalid = self.compact.verify(first["task_id"], "completed-verify")
        state = self.compact.navigator.store.load(first["task_id"])
        self.assertEqual(invalid["error"], "invalid_phase")
        self.assertEqual(state.external_call_count, 1)


if __name__ == "__main__":
    unittest.main()
