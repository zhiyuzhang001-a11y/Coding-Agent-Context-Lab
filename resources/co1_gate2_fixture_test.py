from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


FIXTURE = Path(__file__).with_name("co1_gate2_fixture.py")


def load_fixture():
    spec = importlib.util.spec_from_file_location("co1_gate2_fixture", FIXTURE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Gate2FixtureTests(unittest.TestCase):
    def test_format_label_uses_uppercase_external_representation(self) -> None:
        self.assertEqual(load_fixture().format_label("  Ready  "), "READY")


if __name__ == "__main__":
    unittest.main()
