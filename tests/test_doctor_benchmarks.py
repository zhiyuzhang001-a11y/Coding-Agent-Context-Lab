import json
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

from doctor import run_doctor
from run_benchmarks import run_benchmarks
from run_navigator_benchmark import run_benchmark as run_navigator_benchmark


class DoctorBenchmarkTests(unittest.TestCase):
    def test_doctor_reports_required_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = run_doctor(PLUGIN, Path(temporary) / "data", PLUGIN)
        self.assertEqual(result["status"], "ok")
        required = {item["name"]: item["status"] for item in result["checks"] if item["required"]}
        self.assertEqual(required["python"], "ok")
        self.assertEqual(required["git"], "ok")
        self.assertEqual(required["data_store"], "ok")

    def test_benchmark_cases_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = run_benchmarks(
                PLUGIN,
                PLUGIN / "resources" / "benchmark_cases.json",
                Path(temporary) / "data",
            )
        self.assertEqual(result["status"], "passed", json.dumps(result, indent=2))
        self.assertEqual(result["passed_count"], result["case_count"])

    def test_doctor_accepts_non_git_code_directory_with_explicit_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "installed-plugin"
            root.mkdir()
            result = run_doctor(root, Path(temporary) / "data", root)
        self.assertEqual(result["status"], "ok")
        statuses = {item["name"]: item["status"] for item in result["checks"]}
        self.assertEqual(statuses["git_root"], "warn")
        self.assertEqual(statuses["data_store"], "ok")

    def test_natural_language_navigator_benchmark_passes(self):
        result = run_navigator_benchmark()
        self.assertEqual(result["status"], "passed", json.dumps(result, indent=2))
        self.assertGreaterEqual(result["case_count"], 3)
        self.assertGreater(result["improved_count"], result["case_count"] / 2)


if __name__ == "__main__":
    unittest.main()
