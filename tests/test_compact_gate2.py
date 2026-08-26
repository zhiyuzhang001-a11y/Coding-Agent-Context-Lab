from __future__ import annotations

import sys
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_compact_gate2 import (
    COMPACT_PARAMETERS,
    FROZEN_M2D_FAILURES,
    FROZEN_RESCUE_CASES,
    classify_evidence,
    evidence_hits_target,
)
from run_m2c_benchmark import CASES
from run_m2d_benchmark import SECONDARY_CASES


class CompactGate2ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = {
            "target": "Target.apply",
            "path": "src/target.py",
            "relevant": ("Related",),
        }
        self.evidence = [
            {
                "evidence_id": "target-id",
                "hash": "target-hash",
                "path": "src/target.py",
                "symbol": "Target.apply",
            },
            {
                "evidence_id": "related-id",
                "hash": "related-hash",
                "path": "src/other.py",
                "symbol": "Related",
            },
            {
                "evidence_id": "wrong-id",
                "hash": "wrong-hash",
                "path": "src/wrong.py",
                "symbol": "Wrong",
            },
        ]

    def test_oracle_classifies_only_already_returned_evidence(self) -> None:
        accepted, rejected, uncertain = classify_evidence(self.evidence, self.case)
        self.assertEqual(accepted, ["target-id=target-hash", "related-id=related-hash"])
        self.assertEqual(uncertain, [])
        self.assertEqual(rejected, ["wrong-id=wrong-hash"])
        self.assertTrue(evidence_hits_target(self.evidence[0], self.case))
        self.assertFalse(evidence_hits_target(self.evidence[1], self.case))

    def test_frozen_manifest_has_ten_identifier_free_cases_and_nine_successes(self) -> None:
        cases = [*CASES, *SECONDARY_CASES]
        self.assertEqual(len(cases), 10)
        self.assertEqual(FROZEN_M2D_FAILURES, {"environment-diagnostics"})
        self.assertEqual(len([case for case in cases if case["id"] not in FROZEN_M2D_FAILURES]), 9)
        self.assertTrue(FROZEN_RESCUE_CASES.issubset({case["id"] for case in cases}))

    def test_compact_parameters_are_frozen_to_two_result_protocol(self) -> None:
        self.assertEqual(COMPACT_PARAMETERS["total_budget"], 8400)
        self.assertEqual(COMPACT_PARAMETERS["navigation_budget"], 2400)
        self.assertEqual(COMPACT_PARAMETERS["expansion_budget"], 6000)
        self.assertEqual(COMPACT_PARAMETERS["max_steps"], 8)
        self.assertEqual(COMPACT_PARAMETERS["max_source_reads"], 8)
        self.assertEqual(COMPACT_PARAMETERS["max_hops"], 2)


if __name__ == "__main__":
    unittest.main()
