import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from navigation_contract import ContractError, Edge, Marker, ProviderResult, QueryRequest


class NavigationContractTests(unittest.TestCase):
    def marker(self) -> Marker:
        return Marker(
            repo_id="repo-1",
            path="src/service.py",
            symbol="Service.run",
            kind="method",
            start_line=10,
            end_line=20,
            evidence_hash="abc",
            confidence=0.9,
            base_value=2.0,
            expansion_tokens=120,
            provider="ast",
            signature="def run(self):",
        )

    def test_marker_round_trip_has_stable_id(self):
        marker = self.marker()
        restored = Marker.from_dict(marker.to_dict())
        self.assertEqual(marker, restored)
        self.assertEqual(len(marker.id), 24)

    def test_contract_rejects_absolute_paths_and_bad_confidence(self):
        value = self.marker().to_dict()
        value["path"] = "/private/source.py"
        with self.assertRaises(ContractError):
            Marker.from_dict(value)
        value = self.marker().to_dict()
        value["confidence"] = 1.5
        with self.assertRaises(ContractError):
            Marker.from_dict(value)

    def test_query_and_result_serialize_lists(self):
        marker = self.marker()
        edge = Edge(
            repo_id="repo-1",
            source_id=marker.id,
            target_id="target",
            kind="calls",
            evidence_hash="def",
            confidence=0.8,
            provider="ast",
        )
        request = QueryRequest(task="trace run", budget_tokens=500, symbols=("Service.run",))
        result = ProviderResult(provider="ast", markers=(marker,), edges=(edge,), estimated_tokens=100)
        self.assertEqual(request.to_dict()["symbols"], ["Service.run"])
        self.assertEqual(result.to_dict()["edges"][0]["id"], edge.id)


if __name__ == "__main__":
    unittest.main()
