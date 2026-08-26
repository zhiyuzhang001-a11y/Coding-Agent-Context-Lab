from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("serena_bundle", ROOT / "scripts" / "serena_bundle.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class SerenaBundleTests(unittest.TestCase):
    def test_parses_backend_json_without_double_encoding(self) -> None:
        target = json.dumps([{"name_path": "Service/run", "body": "return 1"}])
        references = json.dumps({"service.py": [{"name_path": "main"}]})
        bundle = module.build_bundle(target, references, 500, 2)
        self.assertIsInstance(bundle["target"], list)
        self.assertIsInstance(bundle["references"], dict)
        self.assertEqual(bundle["backend_calls"], 2)
        self.assertLessEqual(bundle["estimated_output_tokens"], 500)

    def test_truncates_references_before_target(self) -> None:
        target = json.dumps([{"name_path": "Service/run", "body": "x" * 900}])
        references = json.dumps({"refs": ["y" * 5000]})
        bundle = module.build_bundle(target, references, 400, 2)
        self.assertTrue(bundle["truncated"])
        self.assertTrue(bundle["references"]["truncated"])
        self.assertLessEqual(bundle["estimated_output_tokens"], 400)


if __name__ == "__main__":
    unittest.main()
