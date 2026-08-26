from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
RESOURCES = ROOT / "resources"
SCRIPTS = ROOT / "scripts"
PRIVATE_ROOT = WORKSPACE / ".agent-token-manager/acp0-4a-repeat5-20260817"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_acp1_3a_frozen_baseline as baseline  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Acp13aFrozenBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load("acp1_3a_frozen_baseline_spec.json")
        cls.observations = load("acp1_3a_frozen_cycle_observations.json")
        cls.analysis = load("acp1_3a_frozen_cycle_analysis.json")
        cls.index = load("acp1_3a_frozen_baseline_index.json")
        cls.manifest = load("acp1_3a_frozen_experiment_manifest.json")

    def test_all_gates_pass_under_frozen_scope(self) -> None:
        self.assertEqual(self.index["status"], "complete_under_frozen_experiment_scope")
        self.assertEqual(set(self.index["gates"].values()), {True})
        self.assertEqual(self.index["upstream_baseline_id"], "acp1-2-co1-4-cost-necessity-hypothesis-catalog-v1")
        self.assertEqual(self.index["governance"]["case_count"], 12)

    def test_private_source_reextracts_and_outputs_reproduce_byte_for_byte(self) -> None:
        first = baseline._build(PRIVATE_ROOT)
        second = baseline._build(PRIVATE_ROOT)
        self.assertEqual(first[2:], second[2:])
        for name, payload in zip(("observations", "analysis", "markdown", "cli_text"), first[2:]):
            self.assertEqual(payload, (RESOURCES / baseline.OUTPUT_NAMES[name]).read_bytes())
        self.assertTrue(baseline._expected(self.spec, first[0], first[1]))

    def test_manifest_binds_index_and_private_source_without_persisting_path(self) -> None:
        index_path = RESOURCES / "acp1_3a_frozen_baseline_index.json"
        self.assertEqual(self.manifest["artifacts"]["public_compact_result"]["sha256"], sha256(index_path))
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["status"], "produced")
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["visibility"], "private")
        self.assertTrue(all("path" not in artifact for artifact in self.manifest["artifacts"].values()))
        self.assertNotIn(str(PRIVATE_ROOT).lower(), json.dumps(self.manifest).lower())
        self.assertFalse(self.index["source_private_artifact"]["paths_persisted"])

    def test_index_binds_all_public_artifacts(self) -> None:
        for name, artifact in self.index["artifacts"].items():
            with self.subTest(artifact=name):
                path = ROOT / artifact["path"]
                self.assertTrue(path.is_file())
                self.assertEqual(artifact["sha256"], sha256(path))

    def test_primary_and_replication_results_match_frozen_facts(self) -> None:
        self.assertEqual(self.analysis["coverage"]["exact_linked_run_count"], 120)
        self.assertEqual(self.analysis["coverage"]["usage_snapshot_count"], 287)
        off, on = self.analysis["arm_analyses"]
        self.assertEqual([row["incremental_usage"]["total_tokens"]["median"] for row in off["cycle_ordinal_costs"]], [15549, 15958.5, 16969.5, 23042])
        self.assertEqual([row["incremental_usage"]["total_tokens"]["median"] for row in on["cycle_ordinal_costs"]], [15556, 15955, 17043, 23152])
        self.assertEqual(off["cycle_ordinal_costs"][-1]["sample_status"], "insufficient_descriptive_sample")
        self.assertEqual(on["cycle_ordinal_costs"][-1]["sample_status"], "insufficient_descriptive_sample")

    def test_schema_privacy_unknown_and_no_verdict(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        jsonschema.validate(self.observations, load("acp1_3a_cycle_observations_schema.json"))
        jsonschema.validate(self.analysis, load("acp1_3a_cycle_analysis_schema.json"))
        serialized = "\n".join((RESOURCES / name).read_text(encoding="utf-8") for name in (
            "acp1_3a_frozen_cycle_observations.json", "acp1_3a_frozen_cycle_analysis.json",
            "acp1_3a_frozen_cycle_analysis.md", "acp1_3a_frozen_cycle_analysis.txt",
        )).lower()
        for forbidden in ("/users/", "final_text", "tool_response", "wasted_tokens", "avoidable_tokens", "potential_savings"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(set(self.analysis["unknowns"].values()), {"unknown"})
        self.assertTrue(self.analysis["policy"]["descriptive_not_causal"])
        self.assertTrue(self.analysis["policy"]["no_intervention"])

    def test_all_prior_and_online_frozen_hashes_remain_unchanged(self) -> None:
        expected = {
            "resources/acp1_0_frozen_baseline_index.json": "598bf7ea4ee98f17de483b5f818c68d9ea95f5fc444736f1bac1efa34b65a186",
            "resources/acp1_1_frozen_baseline_index.json": "034630b6a8474f1b6d0e7f245fa60098edab0a393642c97762b426123cb43fb9",
            "resources/acp1_2_frozen_catalog_index.json": "e9aa0310cbf6eea4dc33bfe9ba3c8987097919e0956fbc8f801885d30dd24975",
            "resources/acp1_2_frozen_experiment_manifest.json": "5528690350304f62d666acd7aa47288ce922c5b50511b9c09dadbdf5365ade61",
            "scripts/acp_collector.py": "81efee8b5ae05fe2f9c76f73e5edacec1e8269ae5923a6ebc0019f1479f96de2",
            "hooks/hooks.json": "797b72b678ddba104acd93285f3c34542e75a58f69016fb01c99bf4ebac394dd",
        }
        for path, expected_hash in expected.items():
            self.assertEqual(sha256(ROOT / path), expected_hash)


if __name__ == "__main__":
    unittest.main()
