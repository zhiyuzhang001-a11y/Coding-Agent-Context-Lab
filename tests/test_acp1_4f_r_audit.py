from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
CONTRACT = ROOT / "resources/acp1_4f_r_audit_contract.json"
RESULT = ROOT / "resources/acp1_4f_r_audit_result.json"
INDEX = ROOT / "resources/acp1_4f_r_frozen_audit_index.json"
PRIVATE = WORKSPACE / ".agent-token-manager/acp1-4f-native-v21-20260819"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Acp14fRAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = load_module("audit_acp1_4f_native_paths", ROOT / "scripts/audit_acp1_4f_native_paths.py")
        cls.futility = load_module("acp1_4f_futility", ROOT / "scripts/acp1_4f_futility.py")

    def test_contract_preserves_v2_1_and_forbids_new_runs(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertTrue(contract["source_experiment"]["immutable"])
        self.assertFalse(contract["source_experiment"]["historical_reclassification_allowed"])
        self.assertEqual(contract["scope"]["agent_runs"], 0)
        self.assertIn("new_agent_runs", contract["forbidden_inputs"])
        self.assertFalse(contract["downstream_boundary"]["new_experiment_version_created_by_this_audit"])

    def test_checked_in_result_is_reproducible(self) -> None:
        rebuilt = self.audit.build_audit(ROOT, PRIVATE, CONTRACT)
        checked_in = json.loads(RESULT.read_text(encoding="utf-8"))
        self.assertEqual(rebuilt, checked_in)

    def test_frozen_audit_artifact_chain(self) -> None:
        index = json.loads(INDEX.read_text(encoding="utf-8"))
        self.assertEqual(index["agent_run_count"], 0)
        self.assertFalse(index["authorization_boundary"]["development_pool_agent_runs_authorized"])
        for artifact in index["artifacts"].values():
            path = ROOT / artifact["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), artifact["sha256"])

    def test_shell_wrappers_do_not_hide_evidence_carriers(self) -> None:
        self.assertEqual(self.audit.carrier_kind('/bin/zsh -lc "sed -n \'1,200p\' file.py"', "body"), "bash_sed")
        self.assertEqual(self.audit.carrier_kind("/bin/zsh -lc 'rg -n key .'", "file.py:1:key"), "bash_rg")

    def test_result_identifies_evidence_level_stability_without_reclassification(self) -> None:
        result = json.loads(RESULT.read_text(encoding="utf-8"))
        totals = result["totals"]
        self.assertEqual(totals["observed_completed_runs"], 54)
        self.assertEqual(totals["correct_runs"], 54)
        self.assertEqual(totals["measurement_unknown_runs"], 0)
        self.assertEqual(totals["evidence_opportunity_recurrence"], 54)
        self.assertEqual(totals["intervention_compatible_carrier_recurrence"], 54)
        self.assertGreater(totals["identity_false_negative_runs"], 0)
        self.assertTrue(any("PATH_GATE_MISMATCH" in row["diagnostic_labels"] for row in result["case_summaries"]))
        self.assertFalse(result["causal_claims"]["v2_1_reclassified"])
        self.assertFalse(result["causal_claims"]["r1_s1_b1_tested"])

    def test_public_result_has_no_private_bodies_or_paths(self) -> None:
        text = RESULT.read_text(encoding="utf-8")
        for forbidden in ("/Users/", "/var/folders/", "final_text", "raw_command", "aggregated_output", "run_id"):
            self.assertNotIn(forbidden, text)

    def test_case_level_futility_and_family_futility(self) -> None:
        self.assertFalse(self.futility.case_can_still_qualify(4, 10, 4, 0, 0, 4, 9, 8, 0, 8))
        cases = [
            {"case_id": "r1", "family": "read"},
            {"case_id": "r2", "family": "read"},
            {"case_id": "r3", "family": "read"},
            {"case_id": "r4", "family": "read"},
            {"case_id": "s1", "family": "search"},
            {"case_id": "s2", "family": "search"},
            {"case_id": "s3", "family": "search"},
            {"case_id": "s4", "family": "search"},
            {"case_id": "b1", "family": "bash"},
            {"case_id": "b2", "family": "bash"},
            {"case_id": "b3", "family": "bash"},
            {"case_id": "b4", "family": "bash"},
        ]
        states = {"r1": "qualified", "r2": "rejected", "r3": "rejected", "r4": "rejected"}
        result = self.futility.coverage_maximum(cases, states, 9, 3)
        self.assertFalse(result["native_coverage_gate_can_still_pass"])
        self.assertEqual(result["stop_reason"], "STOP_FUTILITY")
        self.assertEqual(result["maximum_qualified_by_family"]["read"], 1)


if __name__ == "__main__":
    unittest.main()
