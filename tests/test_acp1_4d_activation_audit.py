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
PRIVATE_ROOT = WORKSPACE / ".agent-token-manager/acp1-4c-formal-live-20260819"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import audit_acp1_4d_activation as auditor  # noqa: E402
import freeze_acp1_4d_activation_audit as freezer  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Acp14dActivationAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit_spec = load("acp1_4d_activation_audit_spec.json")
        cls.audit = load("acp1_4d_activation_audit.json")
        cls.freeze_spec = load("acp1_4d_frozen_activation_audit_spec.json")
        cls.index = load("acp1_4d_frozen_activation_audit_index.json")
        cls.manifest = load("acp1_4d_frozen_experiment_manifest.json")

    def test_frozen_gate_and_historical_verdicts_are_unchanged(self) -> None:
        self.assertEqual(self.audit["activation_gate"], 0.35)
        self.assertEqual(self.audit["agent_run_count"], 0)
        self.assertTrue(all(row["historical_verdict"] == "INCONCLUSIVE" for row in self.audit["cases"]))
        self.assertFalse(self.audit["policy"]["activation_gate_changed"])
        self.assertFalse(self.audit["policy"]["historical_verdicts_changed"])

    def test_two_rule_mismatches_are_supported_by_composition(self) -> None:
        rows = {row["case_id"]: row for row in self.audit["cases"]}
        read = rows["read_context_router_limit_v1"]
        budget = rows["search_budget_stop_v1"]
        self.assertEqual(read["primary_classification"], "RULE_MISMATCH")
        self.assertEqual(read["findings"]["source_lines_changed"], 23)
        self.assertEqual(budget["primary_classification"], "RULE_MISMATCH")
        self.assertEqual(budget["findings"]["source_lines_changed"], 1)
        self.assertGreater(budget["findings"]["preserved_target_visible_char_share"], 0.73)

    def test_token_search_is_censored_not_reclassified_as_pass(self) -> None:
        row = next(row for row in self.audit["cases"] if row["case_id"] == "search_token_router_v1")
        self.assertEqual(row["primary_classification"], "MEASUREMENT_MISMATCH")
        self.assertEqual(row["findings"]["source_files_changed"], 81)
        self.assertEqual(row["findings"]["source_lines_changed"], 456)
        self.assertEqual(row["findings"]["control_runs_with_truncation"], 10)
        self.assertEqual(row["findings"]["treatment_runs_with_truncation"], 10)
        self.assertLess(row["observed_reduction_median"], 0.01)

    def test_audit_is_deterministic_from_frozen_private_subset(self) -> None:
        rebuilt = auditor.build(RESOURCES / "acp1_4d_activation_audit_spec.json", ROOT, PRIVATE_ROOT)
        self.assertEqual(auditor.canonical_bytes(rebuilt), (RESOURCES / "acp1_4d_activation_audit.json").read_bytes())

    def test_private_inventory_binds_exactly_sixty_runs(self) -> None:
        inventory = freezer.private_inventory(PRIVATE_ROOT)
        digest = hashlib.sha256(freezer.canonical_bytes(inventory)).hexdigest()
        self.assertEqual(inventory["run_count"], 60)
        self.assertEqual(digest, self.freeze_spec["private_source"]["inventory_sha256"])
        self.assertEqual(digest, self.index["private_source"]["inventory_sha256"])

    def test_manifest_and_component_hashes_are_bound(self) -> None:
        index_path = RESOURCES / "acp1_4d_frozen_activation_audit_index.json"
        self.assertEqual(self.manifest["artifacts"]["public_compact_result"]["sha256"], sha256(index_path))
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["visibility"], "private")
        for artifact in self.index["artifacts"].values():
            path = ROOT / artifact["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(artifact["sha256"], sha256(path))

    def test_public_artifacts_preserve_privacy_and_policy_boundary(self) -> None:
        serialized = "\n".join((RESOURCES / name).read_text(encoding="utf-8") for name in (
            "acp1_4d_activation_audit_spec.json", "acp1_4d_activation_audit.json",
            "acp1_4d_frozen_activation_audit_index.json", "acp1_4d_frozen_experiment_manifest.json",
        )).casefold()
        for prohibited in ("/users/", "final_text", "tool_response", "wasted_tokens", "potential_savings"):
            self.assertNotIn(prohibited, serialized)
        self.assertFalse(self.index["policy"]["production_slicing_or_replacement"])
        self.assertFalse(self.index["policy"]["real_time_recommendation"])
        self.assertFalse(self.index["policy"]["global_savings_claim"])


if __name__ == "__main__":
    unittest.main()
