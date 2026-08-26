from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("context_router", SCRIPTS / "context_router.py")
assert spec and spec.loader
router = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = router
spec.loader.exec_module(router)


class ContextRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_small_file_routes_to_full_read(self) -> None:
        path = self.root / "small.py"
        path.write_text("def compact():\n    return 1\n", encoding="utf-8")
        result = router.route_read(path, "compact", ["compact"], 400, cache_dir=self.cache)
        self.assertEqual(result["route"]["reason"], "small_file")
        self.assertEqual(result["mode"], "full")
        self.assertIn("return 1", result["regions"][0]["content"])

    def test_large_file_routes_to_named_symbols_and_cache_hits(self) -> None:
        path = self.root / "large.py"
        path.write_text(
            "def target():\n    return 'needed'\n\n"
            + "def unrelated():\n    values = [\n"
            + "\n".join(f"        'filler-{index}'," for index in range(400))
            + "\n    ]\n    return values\n",
            encoding="utf-8",
        )
        first = router.route_read(path, "", ["target"], 500, cache_dir=self.cache)
        second = router.route_read(path, "", ["target"], 500, cache_dir=self.cache)
        self.assertEqual(first["route"]["reason"], "named_symbols")
        self.assertEqual(first["regions"][0]["name"], "target")
        self.assertNotIn("filler-399", first["regions"][0]["content"])
        self.assertEqual(first["cache_status"], "miss")
        self.assertEqual(second["cache_status"], "hit")

    def test_large_untargeted_file_routes_to_outline(self) -> None:
        path = self.root / "large.py"
        path.write_text("def one():\n    pass\n" + "# filler\n" * 500, encoding="utf-8")
        result = router.route_read(path, "", [], 400, cache_dir=self.cache)
        self.assertEqual(result["route"]["reason"], "large_file_without_target")
        self.assertEqual(result["mode"], "outline")


if __name__ == "__main__":
    unittest.main()
