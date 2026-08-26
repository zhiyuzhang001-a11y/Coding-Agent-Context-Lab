import sys
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_m2c_benchmark import CASES
from run_m2d_benchmark import SECONDARY_CASES
from run_serena_discovery_probe import _parse_symbols, _select_terms


class M2dDiscoveryTests(unittest.TestCase):
    def test_cross_repository_manifest_has_ten_identifier_free_cases(self):
        cases = [*CASES, *SECONDARY_CASES]
        self.assertEqual(len(cases), 10)
        for case in cases:
            task = case["task"].lower()
            self.assertNotIn(case["target"].lower(), task)
            self.assertTrue(case["path"].endswith(".py"))

    def test_serena_shortened_results_normalize_to_marker_identity(self):
        text = (
            'Matched 2>max_matches=1 symbols.\nShortened result:\n'
            '{"src/agent.py":["ToolSet/without_editing_tools"]}'
        )
        self.assertEqual(
            _parse_symbols(text),
            [{"path": "src/agent.py", "symbol": "ToolSet.without_editing_tools"}],
        )

    def test_serena_probe_queries_are_bounded_and_do_not_use_oracle(self):
        case = CASES[1]
        terms = _select_terms(case["task"], 4)
        self.assertLessEqual(len(terms), 4)
        self.assertNotIn(case["target"].lower(), terms)


if __name__ == "__main__":
    unittest.main()
