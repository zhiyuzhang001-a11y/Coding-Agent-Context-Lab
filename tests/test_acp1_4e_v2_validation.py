from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
RESOURCES = ROOT / "resources"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_acp1_4e_v2_validation as runner  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


class Acp14eV2ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load("acp1_4e_experiment_spec.json")
        cls.preflight = load("acp1_4e_offline_preflight.json")

    def test_three_versioned_cases_exactly_supersede_audit_targets(self) -> None:
        self.assertEqual(len(self.spec["cases"]), 3)
        self.assertTrue(all(row["case_version"] == 2 for row in self.spec["cases"]))
        self.assertEqual({row["supersedes"] for row in self.spec["cases"]}, {
            "read_context_router_limit_v1", "search_budget_stop_v1", "search_token_router_v1",
        })

    def test_gate_is_not_relaxed_and_all_three_are_required(self) -> None:
        self.assertEqual(self.spec["offline"]["minimum_evidence_reduction_ratio"], 0.35)
        self.assertEqual(self.spec["formal"]["minimum_evidence_reduction_ratio"], 0.35)
        self.assertEqual(self.spec["qualification"]["qualified_case_min_for_formal"], 3)
        self.assertEqual(self.spec["formal"]["blocks_per_case"], 10)

    def test_commands_have_unambiguous_scope(self) -> None:
        for case in self.spec["cases"]:
            command = case["offline_command"].strip()
            self.assertFalse(command.endswith(" ."))
            self.assertNotIn(" > ", command)
        token = next(row for row in self.spec["cases"] if row["case_id"] == "search_token_router_v2")
        self.assertIn("rg -ni", token["offline_command"])

    def test_offline_preflight_activates_without_censoring(self) -> None:
        self.assertEqual(self.preflight["status"], "pass")
        self.assertEqual(self.preflight["agent_run_count"], 0)
        self.assertEqual(self.preflight["case_count"], 3)
        for row in self.preflight["cases"]:
            self.assertGreaterEqual(row["evidence_reduction_ratio"], 0.35)
            self.assertTrue(all(row["checks"].values()))
        token = next(row for row in self.preflight["cases"] if row["case_id"] == "search_token_router_v2")
        self.assertLess(token["control_chars"], self.spec["offline"]["token_router_censoring_ceiling_chars"])

    def test_treatments_are_deterministic_and_preserve_answer_evidence(self) -> None:
        for case in self.spec["cases"]:
            outputs = []
            metas = []
            for _ in range(2):
                temporary = Path(tempfile.mkdtemp(prefix="acp14e-test-"))
                workdir = temporary / "subject"
                try:
                    runner.base.qualification.materialize_subject(WORKSPACE, self.spec["subject_commit"], workdir)
                    metas.append(runner.apply_treatment(workdir, case))
                    completed = subprocess.run(["/bin/zsh", "-lc", case["offline_command"]], cwd=workdir, text=True, capture_output=True, timeout=30)
                    self.assertEqual(completed.returncode, 0)
                    self.assertIn(case["expected"].casefold(), completed.stdout.casefold())
                    outputs.append(hashlib.sha256(completed.stdout.encode()).hexdigest())
                finally:
                    shutil.rmtree(temporary, ignore_errors=True)
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(metas[0], metas[1])

    def test_policy_and_frozen_upstream_boundaries(self) -> None:
        self.assertTrue(all(not value for value in self.spec["policy"].values()))
        self.assertEqual(runner.sha256_file(RESOURCES / "acp1_4d_frozen_activation_audit_index.json"), runner.FROZEN_HASHES["resources/acp1_4d_frozen_activation_audit_index.json"])
        self.assertEqual(runner.sha256_file(RESOURCES / "acp1_4c_results.json"), runner.FROZEN_HASHES["resources/acp1_4c_results.json"])


if __name__ == "__main__":
    unittest.main()
