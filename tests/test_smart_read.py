from __future__ import annotations

import importlib.util
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("smart_read", ROOT / "scripts" / "smart_read.py")
assert spec and spec.loader
smart_read_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = smart_read_module
spec.loader.exec_module(smart_read_module)


SOURCE = textwrap.dedent(
    '''
    import hashlib

    def login(username: str, password: str) -> bool:
        """Authenticate a user."""
        digest = hashlib.sha256(password.encode()).hexdigest()
        return username == "admin" and bool(digest)

    def cleanup_generated_fixtures() -> None:
        """An unrelated and intentionally verbose helper."""
        values = [
            "fixture-001", "fixture-002", "fixture-003", "fixture-004",
            "fixture-005", "fixture-006", "fixture-007", "fixture-008",
        ]
        for value in values:
            print(value)
    '''
).strip() + "\n"


class SmartReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "auth.py"
        self.path.write_text(SOURCE, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_outline_returns_signatures_without_bodies(self) -> None:
        result = smart_read_module.smart_read(self.path, "", 300, "outline")
        content = result["regions"][0]["content"]
        self.assertIn("function login", content)
        self.assertIn("function cleanup_generated_fixtures", content)
        self.assertNotIn("fixture-008", content)
        self.assertLessEqual(result["estimated_output_tokens"], 300)

    def test_symbol_query_excludes_unrelated_function(self) -> None:
        result = smart_read_module.smart_read(self.path, "login authentication", 300, "auto")
        names = [region["name"] for region in result["regions"]]
        self.assertEqual(result["mode"], "symbol")
        self.assertEqual(names, ["login"])
        self.assertNotIn("fixture-008", result["regions"][0]["content"])
        self.assertEqual(result["omitted_region_count"], 1)

    def test_full_mode_respects_budget(self) -> None:
        result = smart_read_module.smart_read(self.path, "", 180, "full")
        self.assertLessEqual(result["estimated_output_tokens"], 180)
        self.assertTrue(result["truncated"])

    def test_exact_symbols_return_once_in_requested_order(self) -> None:
        result = smart_read_module.smart_read(
            self.path,
            "",
            500,
            "auto",
            ["cleanup_generated_fixtures", "login", "login"],
        )
        self.assertEqual(
            [region["name"] for region in result["regions"]],
            ["cleanup_generated_fixtures", "login"],
        )
        self.assertEqual(result["requested_symbols"], ["cleanup_generated_fixtures", "login", "login"])

    def test_structure_cache_misses_then_hits_without_source_body(self) -> None:
        cache_dir = Path(self.temp.name) / "cache"
        first = smart_read_module.smart_read(self.path, "login", 400, "auto", cache_dir=cache_dir)
        second = smart_read_module.smart_read(self.path, "login", 400, "auto", cache_dir=cache_dir)
        self.assertEqual(first["cache_status"], "miss")
        self.assertEqual(second["cache_status"], "hit")
        cache_text = "\n".join(path.read_text(encoding="utf-8") for path in cache_dir.iterdir())
        self.assertNotIn("fixture-008", cache_text)
        self.assertNotIn("return username", cache_text)

        self.path.write_text(SOURCE + "\ndef added_after_cache():\n    return True\n", encoding="utf-8")
        changed = smart_read_module.smart_read(self.path, "added_after_cache", 400, "auto", cache_dir=cache_dir)
        self.assertEqual(changed["cache_status"], "miss")
        self.assertEqual(changed["regions"][0]["name"], "added_after_cache")

    def test_cache_directory_falls_back_to_private_temp_location(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            cache_dir = smart_read_module.cache_directory_from_environment()
        self.assertIsNotNone(cache_dir)
        self.assertEqual(cache_dir.name, "agent-token-manager-parse-cache")


if __name__ == "__main__":
    unittest.main()
