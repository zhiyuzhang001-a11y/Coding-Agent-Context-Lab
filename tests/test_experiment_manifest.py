from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_experiment_manifest import ARTIFACT_NAMES, build_manifest, canonical_bytes  # noqa: E402


class ExperimentManifestTests(unittest.TestCase):
    def descriptor(self, artifact_path: Path) -> dict:
        artifacts = {
            name: {"status": "not_produced", "visibility": "public"}
            for name in ARTIFACT_NAMES
        }
        artifacts["fixture"] = {
            "status": "produced",
            "path": str(artifact_path),
            "visibility": "public",
        }
        artifacts["raw_private_artifact"]["visibility"] = "private"
        return {
            "phase": "acp-1.0-contract-test",
            "started_at": "2026-08-18T01:00:00Z",
            "completed_at": "2026-08-18T01:01:00Z",
            "time_block": "2026-08-18T01:00Z",
            "environment": {
                "codex_version": "test-host",
                "model_identifier": "test-model",
                "reasoning_effort": "test",
                "os": "test-os",
                "architecture": "test-arch",
                "hook_api_version": "unknown",
                "collector_sha256": "0" * 64,
                "normalizer_sha256": "1" * 64,
                "reporter_sha256": "2" * 64,
            },
            "artifacts": artifacts,
        }

    def test_deterministic_chain_and_privacy_safe_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "fixture-private-name.json"
            artifact.write_bytes(b"fixture-one")
            descriptor = self.descriptor(artifact)
            first = build_manifest(descriptor)
            second = build_manifest(descriptor)
            self.assertEqual(canonical_bytes(first), canonical_bytes(second))
            serialized = json.dumps(first, sort_keys=True)
            self.assertNotIn(temp_dir, serialized)
            self.assertNotIn("fixture-private-name", serialized)
            self.assertEqual(first["artifacts"]["fixture"]["sha256"], hashlib.sha256(b"fixture-one").hexdigest())
            self.assertEqual(first["artifacts"]["normalized_result"]["status"], "not_produced")
            self.assertIsNone(first["artifacts"]["normalized_result"]["sha256"])
            self.assertTrue(first["privacy_policy"]["hashes_only_for_artifacts"])

    def test_artifact_change_changes_chain_and_experiment_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "fixture.json"
            artifact.write_bytes(b"one")
            first = build_manifest(self.descriptor(artifact))
            artifact.write_bytes(b"two")
            second = build_manifest(self.descriptor(artifact))
            self.assertNotEqual(first["chain_sha256"], second["chain_sha256"])
            self.assertNotEqual(first["experiment_id"], second["experiment_id"])

    def test_rejects_unallowlisted_environment_and_invalid_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "fixture.json"
            artifact.write_bytes(b"one")
            descriptor = self.descriptor(artifact)
            descriptor["environment"]["SECRET_TOKEN"] = "must-not-persist"
            with self.assertRaises(ValueError):
                build_manifest(descriptor)

            descriptor = self.descriptor(artifact)
            descriptor["artifacts"]["fixture"] = {"status": "produced", "visibility": "public"}
            with self.assertRaises(ValueError):
                build_manifest(descriptor)

            descriptor = self.descriptor(artifact)
            descriptor["artifacts"]["fact_report"]["path"] = str(artifact)
            with self.assertRaises(ValueError):
                build_manifest(descriptor)

    def test_schema_accepts_generated_manifest_when_jsonschema_is_available(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "fixture.json"
            artifact.write_bytes(b"one")
            manifest = build_manifest(self.descriptor(artifact))
        schema = json.loads((ROOT / "resources" / "acp0h_experiment_manifest_schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(manifest, schema)


if __name__ == "__main__":
    unittest.main()
