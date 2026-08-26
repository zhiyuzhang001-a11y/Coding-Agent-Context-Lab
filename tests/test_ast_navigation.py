import json
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

from ast_navigation_provider import AstNavigationProvider, estimate_tokens
from navigation_contract import QueryRequest


class AstNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "sample_repo"
        self.data = base / "data"
        (self.root / "pkg").mkdir(parents=True)
        (self.root / "pkg" / "__init__.py").write_text(
            "from .service import RankingCore\n", encoding="utf-8"
        )
        (self.root / "pkg" / "service.py").write_text(
            "def register(value):\n"
            "    return value\n\n"
            "class BaseRanker:\n"
            "    pass\n\n"
            "class ExternalRanker(ThirdPartyBase):\n"
            "    pass\n\n"
            "@register\n"
            "class RankingCore(BaseRanker):\n"
            "    def score(self, value: int) -> int:\n"
            "        secret = 'TOP SECRET BODY'\n"
            "        return value + 1\n\n"
            "def helper() -> str:\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        (self.root / "consumer.py").write_text(
            "from pkg.service import RankingCore\n\n"
            "def run_rank(value: int) -> int:\n"
            "    return RankingCore().score(value)\n\n"
            "def dynamic_rank(obj, value):\n"
            "    return obj.score(value)\n\n"
            "def register_handler(handler):\n"
            "    return handler\n\n"
            "HANDLER = register_handler(run_rank)\n",
            encoding="utf-8",
        )
        self.provider = AstNavigationProvider(self.root, self.data)

    def tearDown(self):
        self.temporary.cleanup()

    def test_index_is_incremental_and_stores_no_source_body(self):
        first = self.provider.index()
        self.assertFalse(first.warnings)
        self.assertEqual(self.provider.last_index_stats["discovered_files"], 3)
        self.assertEqual(self.provider.last_index_stats["changed_files"], 3)
        counts = self.provider.store.counts()
        self.assertGreaterEqual(counts["markers"], 10)
        self.assertGreaterEqual(self.provider.last_index_stats["import_edges"], 2)
        database_bytes = self.provider.workspace.database.read_bytes()
        self.assertNotIn(b"TOP SECRET BODY", database_bytes)

        self.provider.index()
        self.assertEqual(self.provider.last_index_stats["changed_files"], 0)
        self.assertEqual(self.provider.last_index_stats["unchanged_files"], 3)
        self.assertEqual(self.provider.store.counts(), counts)

    def test_changed_and_deleted_files_are_updated_locally(self):
        self.provider.index()
        service = self.root / "pkg" / "service.py"
        service.write_text(service.read_text(encoding="utf-8") + "\ndef new_score():\n    return 2\n", encoding="utf-8")
        self.provider.index()
        self.assertEqual(self.provider.last_index_stats["changed_files"], 1)
        self.assertEqual(self.provider.last_index_stats["unchanged_files"], 2)
        symbols = {marker.symbol for marker in self.provider.store.load_markers(self.provider.name)}
        self.assertIn("new_score", symbols)

        (self.root / "consumer.py").unlink()
        self.provider.index()
        self.assertEqual(self.provider.last_index_stats["deleted_files"], 1)
        paths = {marker.path for marker in self.provider.store.load_markers(self.provider.name)}
        self.assertNotIn("consumer.py", paths)

    def test_repeated_definitions_collapse_to_one_semantic_marker(self):
        repeated = self.root / "overloads.py"
        repeated.write_text(
            "def parse(value: int) -> int: ...\n\n"
            "def parse(value: str) -> str: ...\n\n"
            "def parse(value):\n"
            "    return value\n",
            encoding="utf-8",
        )

        result = self.provider.index()

        self.assertFalse(result.warnings)
        markers = [
            marker
            for marker in self.provider.store.load_markers(self.provider.name)
            if marker.path == "overloads.py" and marker.symbol == "parse"
        ]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0].signature, "def parse(value)")

    def test_query_is_ranked_explainable_budgeted_and_private(self):
        self.provider.index()
        request = QueryRequest(
            task="fix search ranking score",
            symbols=("RankingCore",),
            budget_tokens=800,
            include_edge_kinds=("contains", "imports"),
        )
        result = self.provider.query(request)
        payload = result.to_dict()
        self.assertTrue(result.markers)
        self.assertEqual(result.markers[0].symbol, "RankingCore")
        ranking = result.markers[0].metadata["ranking"]
        self.assertIn("components", ranking)
        self.assertIn("reason", ranking)
        self.assertLessEqual(estimate_tokens(payload), request.budget_tokens)
        self.assertNotIn("TOP SECRET BODY", json.dumps(payload))

        relation_request = QueryRequest(
            task="trace ranking implementation relationships",
            budget_tokens=300,
            include_edge_kinds=("inherits", "calls", "references"),
        )
        relation_payload = self.provider.query(relation_request).to_dict()
        self.assertLessEqual(estimate_tokens(relation_payload), relation_request.budget_tokens)

    def test_inherits_calls_and_high_value_references_are_resolved(self):
        self.provider.index()
        markers = {marker.symbol: marker for marker in self.provider.store.load_markers(self.provider.name)}
        edges = self.provider.store.load_edges(self.provider.name)

        self.assertTrue(
            any(
                edge.kind == "inherits"
                and edge.source_id == markers["RankingCore"].id
                and edge.target_id == markers["BaseRanker"].id
                for edge in edges
            )
        )
        self.assertTrue(
            any(
                edge.kind == "calls"
                and edge.source_id == markers["run_rank"].id
                and edge.target_id == markers["RankingCore"].id
                for edge in edges
            )
        )
        reference_kinds = {
            edge.metadata.get("reference_kind")
            for edge in edges
            if edge.kind == "references"
        }
        self.assertIn("symbol_import", reference_kinds)
        self.assertIn("decorator", reference_kinds)
        self.assertIn("registration", reference_kinds)

        unresolved = self.provider.store.load_unresolved_relations(self.provider.name)
        external = next(
            relation
            for relation in unresolved
            if relation["source_symbol"] == "ExternalRanker"
            and relation["target_name"] == "ThirdPartyBase"
            and relation["kind"] == "inherits"
        )
        self.assertLessEqual(external["confidence"], 0.35)
        self.assertEqual(
            external["metadata"]["resolution"], "unresolved_external_or_ambiguous"
        )

        dynamic = markers["dynamic_rank"]
        score = markers["RankingCore.score"]
        self.assertFalse(
            any(
                edge.kind == "calls"
                and edge.source_id == dynamic.id
                and edge.target_id == score.id
                for edge in edges
            )
        )

    def test_semantic_edges_increment_and_delete_without_dangling_targets(self):
        self.provider.index()
        first_counts = self.provider.store.counts()
        self.provider.index()
        self.assertEqual(self.provider.last_index_stats["changed_files"], 0)
        self.assertEqual(self.provider.store.counts(), first_counts)

        (self.root / "consumer.py").unlink()
        self.provider.index()
        marker_ids = {
            marker.id for marker in self.provider.store.load_markers(self.provider.name)
        }
        edges = self.provider.store.load_edges(self.provider.name)
        self.assertTrue(all(edge.source_id in marker_ids and edge.target_id in marker_ids for edge in edges))
        unresolved = self.provider.store.load_unresolved_relations(self.provider.name)
        self.assertTrue(all(relation["source_id"] in marker_ids for relation in unresolved))

    def test_invalidate_removes_only_requested_path(self):
        self.provider.index()
        removed = self.provider.invalidate(["consumer.py"])
        self.assertGreater(removed, 0)
        paths = {marker.path for marker in self.provider.store.load_markers(self.provider.name)}
        self.assertNotIn("consumer.py", paths)
        self.assertIn("pkg/service.py", paths)


if __name__ == "__main__":
    unittest.main()
