from contextlib import closing
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workspace_data import initialize_store, persistent_cache_directory, resolve_data_dir


class WorkspaceDataTests(unittest.TestCase):
    def test_explicit_store_is_private_and_versioned(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            target = Path(temporary) / "data"
            store = initialize_store(root, target)
            self.assertEqual(store.data_dir, target.resolve())
            self.assertEqual(store.database.stat().st_mode & 0o777, 0o600)
            metadata = json.loads((target / "metadata.json").read_text())
            self.assertEqual(metadata["schema_version"], "1")
            with closing(sqlite3.connect(store.database)) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue(
                {"schema_meta", "markers", "edges", "indexed_files", "navigation_tasks"}.issubset(tables)
            )

    def test_environment_store_is_scoped_by_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            base = Path(temporary) / "plugin-data"
            with mock.patch.dict(os.environ, {"AGENT_TOKEN_MANAGER_DATA": str(base)}, clear=False):
                target = resolve_data_dir(root)
            self.assertEqual(target.parent, (base / "projects").resolve())
            self.assertEqual(len(target.name), 20)

    def test_persistent_cache_uses_repository_store(self):
        plugin = Path(__file__).resolve().parents[1]
        cache = persistent_cache_directory(plugin / "scripts" / "smart_read.py")
        self.assertEqual(cache.name, "parse-cache")
        if cache.parent.name != ".agent-token-manager":
            self.assertEqual(cache.parent.parent.name, "agent-token-manager-workspace-cache")

    def test_persistent_cache_uses_private_temp_when_store_is_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "installed" / "scripts" / "smart_read.py"
            target.parent.mkdir(parents=True)
            target.write_text("# fixture\n", encoding="utf-8")
            with mock.patch("workspace_data.initialize_store", side_effect=OSError("read only")):
                cache = persistent_cache_directory(target)
        self.assertEqual(cache.name, "parse-cache")
        self.assertEqual(cache.parent.parent.name, "agent-token-manager-workspace-cache")


if __name__ == "__main__":
    unittest.main()
