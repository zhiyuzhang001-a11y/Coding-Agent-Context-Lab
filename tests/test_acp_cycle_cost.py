from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
RESOURCES = ROOT / "resources"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import acp_cycle_cost as cycle_cost  # noqa: E402
import acp_cycle_cost_renderer as renderer  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


class AcpCycleCostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load("acp1_3a_cycle_fixture.json")

    def test_fixture_freezes_increment_and_transition_semantics(self) -> None:
        report = cycle_cost.analyze_observations(self.fixture)
        off = report["arm_analyses"][0]
        self.assertEqual(off["arm"], "off")
        self.assertEqual(off["cycle_ordinal_costs"][1]["incremental_usage"]["total_tokens"]["median"], 120)
        transition = off["within_run_transitions"][0]
        self.assertEqual(transition["incremental_total_token_delta"]["median"], 20)
        self.assertEqual(transition["incremental_total_token_ratio"]["median"], 1.2)
        self.assertEqual(transition["sample_status"], "insufficient_descriptive_sample")

    def test_analysis_is_deterministic_and_does_not_mutate_input(self) -> None:
        source = copy.deepcopy(self.fixture)
        first = cycle_cost.analyze_observations(source)
        second = cycle_cost.analyze_observations(source)
        self.assertEqual(cycle_cost.canonical_bytes(first), cycle_cost.canonical_bytes(second))
        self.assertEqual(source, self.fixture)

    def test_off_is_primary_and_on_is_unpooled_replication(self) -> None:
        report = cycle_cost.analyze_observations(self.fixture)
        self.assertFalse(report["source_and_scope"]["arms_pooled"])
        self.assertEqual([row["role"] for row in report["arm_analyses"]], [
            "primary_native_analysis", "independent_replication",
        ])

    def test_new_history_causality_and_necessity_remain_unknown(self) -> None:
        report = cycle_cost.analyze_observations(self.fixture)
        self.assertEqual(set(report["unknowns"].values()), {"unknown"})
        self.assertTrue(report["policy"]["descriptive_not_causal"])
        self.assertTrue(report["policy"]["no_waste_or_savings_estimate"])
        self.assertTrue(report["policy"]["no_intervention"])

    def test_tampered_increment_is_rejected(self) -> None:
        source = copy.deepcopy(self.fixture)
        source["runs"][0]["cycles"][1]["incremental_usage"]["input_tokens"] += 1
        source["runs"][0]["cycles"][1]["incremental_usage"]["total_tokens"] += 1
        with self.assertRaisesRegex(cycle_cost.CycleCostError, "increment"):
            cycle_cost.analyze_observations(source)

    def test_renderer_adds_no_metrics_or_verdict(self) -> None:
        report = cycle_cost.analyze_observations(self.fixture)
        markdown = renderer.render_markdown(report)
        text = renderer.render_text(report)
        self.assertIn("insufficient_descriptive_sample", markdown)
        self.assertIn("new-vs-history", text)
        lowered = (markdown + text).lower()
        for forbidden in ("wasted_tokens", "avoidable_tokens", "potential_savings", "savings_ratio"):
            self.assertNotIn(forbidden, lowered)

    def test_fixture_and_analysis_validate_against_schemas(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        jsonschema.validate(self.fixture, load("acp1_3a_cycle_observations_schema.json"))
        jsonschema.validate(cycle_cost.analyze_observations(self.fixture), load("acp1_3a_cycle_analysis_schema.json"))

    def test_frozen_private_source_extracts_120_exact_links_without_private_bodies(self) -> None:
        private_root = WORKSPACE / ".agent-token-manager/acp0-4a-repeat5-20260817"
        observations = cycle_cost.extract_private_runs(private_root)
        summary = observations["source_summary"]
        self.assertEqual(summary["run_count"], 120)
        self.assertEqual(summary["exact_linked_run_count"], 120)
        self.assertEqual(summary["arm_counts"], {"off": 60, "on": 60})
        self.assertEqual(summary["case_count"], 12)
        self.assertEqual(sum(row["cycle_count"] for row in observations["runs"]), 287)
        serialized = cycle_cost.canonical_bytes(observations).decode("utf-8").lower()
        self.assertNotIn("/users/", serialized)
        self.assertNotIn("final_text", serialized)
        self.assertNotIn("expected", serialized)
        self.assertFalse(observations["policy"]["private_bodies_emitted"])

    def test_co1_4_cycle_state_remains_unknown_and_is_not_used_as_source(self) -> None:
        attribution = load("acp1_0_frozen_attribution.json")
        self.assertEqual(attribution["cycle_structure_or_unknown"]["status"], "unknown")
        self.assertEqual(attribution["cycle_structure_or_unknown"]["cycles"], [])


if __name__ == "__main__":
    unittest.main()
