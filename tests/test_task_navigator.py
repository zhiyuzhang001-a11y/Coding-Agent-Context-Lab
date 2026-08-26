import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

from task_navigator import Feedback, STOP_REASONS, TaskNavigator
class TaskNavigatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "repo"
        self.data = base / "data"
        self.root.mkdir()
        (self.root / "workflow.py").write_text(
            "class BaseCoordinator:\n"
            "    pass\n\n"
            "class GenericCoordinator(BaseCoordinator):\n"
            "    pass\n\n"
            "class OptionalToolRegistry:\n"
            "    pass\n\n"
            "def process_login_request(session):\n"
            "    return reject_expired_credentials(session)\n\n"
            "def reject_expired_credentials(session):\n"
            "    secret = 'NAVIGATOR SECRET BODY'\n"
            "    return session.expires_at > 0\n",
            encoding="utf-8",
        )
        self.navigator = TaskNavigator(self.root, self.data)
        self.navigator.provider.index()

    def tearDown(self):
        self.temporary.cleanup()

    def marker(self, symbol):
        return next(
            marker
            for marker in self.navigator.provider.store.load_markers(self.navigator.provider.name)
            if marker.symbol == symbol
        )

    def start(self, task_id=None, total=1800, navigation=500, expansion=1200):
        return self.navigator.start(
            "stop stale login sessions from getting access",
            total,
            navigation,
            expansion,
            task_id=task_id,
            hypotheses=["expiry is not checked"],
        )

    def test_tasks_are_isolated_and_track_seen_selected(self):
        first = self.start("first")
        second = self.start("second")
        result = self.navigator.next(first.task_id)
        first_after = self.navigator.store.load(first.task_id)
        second_after = self.navigator.store.load(second.task_id)
        self.assertTrue(first_after.seen)
        self.assertEqual(len(first_after.selected), 1)
        self.assertEqual(result["candidate"]["id"], first_after.selected[0])
        self.assertFalse(second_after.seen)
        self.assertFalse(second_after.selected)

        next_result = self.navigator.next(first.task_id)
        self.assertNotEqual(result["candidate"]["id"], next_result["candidate"]["id"])

    def test_expansion_feedback_dedup_and_hash_change(self):
        state = self.start()
        target = self.marker("reject_expired_credentials")
        first = self.navigator.expand(state.task_id, target.id, 500)
        self.assertGreater(first["tokens_consumed"], 0)
        self.assertEqual(first["evidence"]["route"]["reason"], "forced_named_symbols")
        self.assertEqual([region["name"] for region in first["evidence"]["regions"]], [target.symbol])
        self.assertEqual(first["feedback"]["source"], "automatic")
        self.assertIn("relevance", first["feedback"])
        after_first = self.navigator.store.load(state.task_id)
        consumed = after_first.expansion_tokens
        self.assertTrue(after_first.expanded)
        self.assertNotIn(b"NAVIGATOR SECRET BODY", self.navigator.provider.workspace.database.read_bytes())

        duplicate = self.navigator.expand(state.task_id, target.id, 500)
        self.assertEqual(duplicate["status"], "duplicate_suppressed")
        self.assertEqual(duplicate["tokens_consumed"], 0)
        self.assertEqual(self.navigator.store.load(state.task_id).expansion_tokens, consumed)

        forced = self.navigator.expand(state.task_id, target.id, 500, force=True)
        self.assertNotEqual(forced["status"], "duplicate_suppressed")
        self.assertGreater(self.navigator.store.load(state.task_id).expansion_tokens, consumed)

        workflow = self.root / "workflow.py"
        workflow.write_text(workflow.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
        self.navigator.provider.index(changed_paths=["workflow.py"])
        changed = self.marker("reject_expired_credentials")
        reread = self.navigator.expand(state.task_id, changed.id, 500)
        self.assertNotEqual(reread["status"], "duplicate_suppressed")
        self.assertGreater(reread["tokens_consumed"], 0)

    def test_feedback_changes_ranking_and_verifies_marker(self):
        state = self.start()
        source = self.marker("process_login_request")
        target = self.marker("reject_expired_credentials")
        before = [marker.id for _, marker, _ in self.navigator.rank(state)]
        before_position = before.index(target.id)
        updated = self.navigator.feedback(
            state.task_id,
            Feedback(
                marker_id=source.id,
                relevance="relevant",
                information_gain="high",
                new_symbols=["reject_expired_credentials"],
                hypotheses_supported=["expiry is not checked"],
                next_action_hint="inspect the discovered validation function",
            ),
        )
        after_ranked = self.navigator.rank(updated)
        after = [marker.id for _, marker, _ in after_ranked]
        after_position = after.index(target.id)
        target_components = next(components for _, marker, components in after_ranked if marker.id == target.id)
        self.assertLess(after_position, before_position)
        self.assertGreater(target_components["feedback_boost"], 0)
        self.assertIn(source.id, updated.verified)
        self.assertNotIn("expiry is not checked", updated.unresolved_hypotheses)

    def test_relevant_feedback_expands_relationship_neighbors_with_reason(self):
        state = self.start()
        base = self.marker("BaseCoordinator")
        child = self.marker("GenericCoordinator")
        updated = self.navigator.feedback(
            state.task_id,
            Feedback(base.id, relevance="relevant", information_gain="high"),
        )
        ranked = self.navigator.rank(updated)
        components = next(
            components for _, marker, components in ranked if marker.id == child.id
        )
        self.assertGreater(components["relationship_boost"], 0)
        reasons = components["relationship_reasons"]
        self.assertTrue(
            any(
                reason["edge_kind"] == "inherits"
                and reason["source_marker_id"] == base.id
                and reason["direction"] == "outgoing"
                for reason in reasons
            )
        )

    def test_relationship_direction_prefers_direct_call_over_module_parent(self):
        state = self.start()
        parent = self.marker("workflow")
        method = self.marker("process_login_request")
        target = self.marker("reject_expired_credentials")
        updated = self.navigator.feedback(
            state.task_id,
            Feedback(method.id, relevance="relevant", information_gain="high"),
        )
        ranked = self.navigator.rank(updated)
        components = {marker.id: values for _, marker, values in ranked}
        self.assertLess(
            components[parent.id]["relationship_boost"],
            components[target.id]["relationship_boost"],
        )

    def test_uncertain_discovered_symbol_is_weaker_than_verified_relationship(self):
        state = self.start()
        source = self.marker("process_login_request")
        target = self.marker("reject_expired_credentials")
        updated = self.navigator.feedback(
            state.task_id,
            Feedback(
                source.id,
                relevance="uncertain",
                information_gain="high",
                new_symbols=[target.symbol],
            ),
        )
        uncertain = next(
            values for _, marker, values in self.navigator.rank(updated) if marker.id == target.id
        )
        verified = self.navigator.feedback(
            state.task_id,
            Feedback(source.id, relevance="relevant", information_gain="high"),
        )
        relevant = next(
            values for _, marker, values in self.navigator.rank(verified) if marker.id == target.id
        )
        self.assertEqual(uncertain["feedback_boost"], 2.0)
        self.assertGreater(relevant["relationship_boost"], uncertain["relationship_boost"])

    def test_irrelevant_agent_assessment_invalidates_automatic_discoveries(self):
        state = self.start()
        source = self.marker("process_login_request")
        target = self.marker("reject_expired_credentials")
        self.navigator.feedback(
            state.task_id,
            Feedback(
                source.id,
                relevance="uncertain",
                information_gain="high",
                new_symbols=[target.symbol],
                source="automatic",
            ),
        )
        updated = self.navigator.feedback(
            state.task_id,
            Feedback(source.id, relevance="irrelevant", information_gain="low"),
        )
        target_components = next(
            values for _, marker, values in self.navigator.rank(updated) if marker.id == target.id
        )
        self.assertEqual(target_components["feedback_boost"], 0.0)

    def test_hard_budget_and_stop_reason(self):
        state = self.navigator.start(
            "stop stale login sessions",
            total_budget=300,
            navigation_budget=0,
            expansion_budget=300,
        )
        target = self.marker("reject_expired_credentials")
        result = self.navigator.expand(state.task_id, target.id, 300)
        updated = self.navigator.store.load(state.task_id)
        self.assertLessEqual(updated.consumed_tokens, 300)
        self.assertLessEqual(result.get("tokens_consumed", 0), 300)

        stopped = self.navigator.stop(state.task_id, "target_found", [target.id])
        self.assertEqual(stopped.stop_reason, "target_found")
        self.assertEqual(stopped.stop_evidence, [target.id])
        self.assertIn(stopped.stop_reason, STOP_REASONS)
        self.assertIn("remaining_budget", stopped.to_dict())
        with self.assertRaises(ValueError):
            self.navigator.stop(state.task_id, "user_stopped")

        no_navigation = self.navigator.start(
            "another natural language task",
            total_budget=300,
            navigation_budget=0,
            expansion_budget=300,
        )
        exhausted = self.navigator.next(no_navigation.task_id)
        self.assertEqual(exhausted["task"]["stop_reason"], "budget_exhausted")

    def test_metadata_overflow_is_omitted_without_exceeding_budget(self):
        state = self.start(total=400, navigation=0, expansion=400)
        module = self.marker("workflow")
        result = self.navigator.expand(state.task_id, module.id, 128)
        self.assertLessEqual(result["tokens_consumed"], 128)
        self.assertIn(result["evidence"].get("status", "active"), {"active", "omitted"})

    def test_unexpandable_nested_symbol_does_not_crash_task(self):
        workflow = self.root / "workflow.py"
        workflow.write_text(
            workflow.read_text(encoding="utf-8")
            + "\ndef outer():\n    def inner():\n        return 1\n    return inner()\n",
            encoding="utf-8",
        )
        self.navigator.provider.index(changed_paths=["workflow.py"])
        state = self.start(total=800, navigation=0, expansion=800)
        nested = self.marker("outer.inner")
        result = self.navigator.expand(state.task_id, nested.id, 300)
        self.assertEqual(result["evidence"].get("status"), "unavailable")
        self.assertIsNone(self.navigator.store.load(state.task_id).stop_reason)

    def test_resolved_feedback_stops_with_evidence(self):
        state = self.start()
        target = self.marker("reject_expired_credentials")
        stopped = self.navigator.feedback(
            state.task_id,
            Feedback(target.id, relevance="relevant", information_gain="high"),
            resolved=True,
        )
        self.assertEqual(stopped.stop_reason, "evidence_sufficient")
        self.assertIn(target.id, stopped.stop_evidence)

    def test_state_persists_across_navigator_instances(self):
        state = self.start("persistent")
        self.navigator.next(state.task_id)
        reopened = TaskNavigator(self.root, self.data)
        restored = reopened.store.load(state.task_id)
        self.assertEqual(restored.task_id, state.task_id)
        self.assertEqual(restored.repo_id, state.repo_id)
        self.assertTrue(restored.selected)

    def test_duplicate_task_id_is_rejected(self):
        self.start("same-id")
        with self.assertRaises(ValueError):
            self.start("same-id")

    def test_bounded_text_discovery_returns_markers_without_source_body(self):
        state = self.navigator.start(
            "reject expired credentials during login validation",
            total_budget=900,
            navigation_budget=400,
            expansion_budget=500,
        )
        result = self.navigator.discover(state.task_id, budget_tokens=300)
        target = self.marker("reject_expired_credentials")
        hit_ids = [hit["marker_id"] for hit in result["discovery"]["hits"]]
        self.assertIn(target.id, hit_ids)
        self.assertNotIn("NAVIGATOR SECRET BODY", str(result))
        restored = self.navigator.store.load(state.task_id)
        self.assertGreater(restored.discovery_tokens, 0)
        self.assertEqual(restored.discovery_tokens, result["tokens_consumed"])
        self.assertLessEqual(restored.consumed_tokens, restored.total_budget)

    def test_duplicate_discovery_query_is_suppressed(self):
        state = self.navigator.start(
            "reject expired credentials during login validation",
            total_budget=900,
            navigation_budget=400,
            expansion_budget=500,
        )
        first = self.navigator.discover(state.task_id, budget_tokens=250)
        consumed = self.navigator.store.load(state.task_id).consumed_tokens
        duplicate = self.navigator.discover(state.task_id, budget_tokens=250)
        self.assertEqual(duplicate["status"], "duplicate_suppressed")
        self.assertEqual(duplicate["tokens_consumed"], 0)
        self.assertEqual(self.navigator.store.load(state.task_id).consumed_tokens, consumed)
        self.assertGreater(first["tokens_consumed"], 0)

    def test_two_irrelevant_candidates_trigger_bounded_rescue(self):
        state = self.start(total=1800, navigation=700, expansion=1000)
        first = self.marker("BaseCoordinator")
        second = self.marker("GenericCoordinator")
        self.navigator.feedback(state.task_id, Feedback(first.id, relevance="irrelevant"))
        self.navigator.feedback(state.task_id, Feedback(second.id, relevance="irrelevant"))
        result = self.navigator.next(state.task_id)
        restored = self.navigator.store.load(state.task_id)
        self.assertEqual(result["discovery_trigger"], "two_consecutive_irrelevant_candidates")
        self.assertEqual(len(restored.discovery_queries), 1)
        self.assertGreater(restored.discovery_tokens, 0)
        self.assertIn("discovery_boost", result["candidate"]["ranking"])

    def test_premature_low_gain_stop_requires_available_rescue(self):
        state = self.start(total=1800, navigation=700, expansion=1000)
        first = self.marker("BaseCoordinator")
        second = self.marker("GenericCoordinator")
        self.navigator.feedback(state.task_id, Feedback(first.id, relevance="irrelevant"))
        self.navigator.feedback(state.task_id, Feedback(second.id, relevance="irrelevant"))
        with self.assertRaisesRegex(ValueError, "premature"):
            self.navigator.stop(state.task_id, "low_expected_gain")

    def test_irrelevant_feedback_terms_do_not_enter_discovery_query(self):
        state = self.start(total=1800, navigation=700, expansion=1000)
        source = self.marker("process_login_request")
        self.navigator.feedback(
            state.task_id,
            Feedback(
                source.id,
                relevance="irrelevant",
                new_symbols=["misleading_branch_term"],
            ),
        )
        terms = self.navigator._active_query_terms(self.navigator.store.load(state.task_id))
        self.assertNotIn("misleading", terms)
        self.assertNotIn("branch", terms)


if __name__ == "__main__":
    unittest.main()
