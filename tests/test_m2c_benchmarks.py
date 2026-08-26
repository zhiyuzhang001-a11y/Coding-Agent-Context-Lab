import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_m2c_benchmark import CASES, has_code_identifier
from run_unified_provider_benchmark import run_codebase_memory


class M2cBenchmarkSchemaTests(unittest.TestCase):
    def test_real_case_schema_has_five_identifier_free_tasks(self):
        self.assertGreaterEqual(len(CASES), 5)
        self.assertEqual(len({case["id"] for case in CASES}), len(CASES))
        for case in CASES:
            self.assertFalse(has_code_identifier(case))
            self.assertTrue(case["path"].endswith(".py"))
            self.assertIn(".", case["target"])

    def test_missing_codebase_memory_degrades_without_blocking(self):
        with patch("run_unified_provider_benchmark.shutil.which", return_value=None):
            result = run_codebase_memory(Path("."))
        self.assertEqual(result["status"], "skipped")
        self.assertTrue(result["degraded_without_blocking_builtin"])


if __name__ == "__main__":
    unittest.main()
