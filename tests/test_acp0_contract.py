from __future__ import annotations

import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"


class Acp0ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((RESOURCES / "acp0_contract.json").read_text(encoding="utf-8"))
        cls.fixture = json.loads((RESOURCES / "acp0_co1_4_replay_fixture.json").read_text(encoding="utf-8"))

    def test_contract_versions_and_closed_privacy_allowlist(self) -> None:
        event = self.contract["event_schema"]
        privacy = self.contract["privacy_schema"]
        self.assertEqual(event["id"], "acp-event-v1")
        self.assertEqual(self.contract["measurement_contract"]["id"], "acp-measurement-v1")
        self.assertEqual(privacy["id"], "acp-privacy-v1")
        self.assertFalse(event["additional_fields_allowed"])
        self.assertEqual(set(event["required_fields"]), set(privacy["allowed_event_fields"]))
        self.assertIn("full_command", privacy["forbidden_data_classes"])
        self.assertIn("absolute_path", privacy["forbidden_data_classes"])
        self.assertIn("raw_session_turn_or_tool_use_id", privacy["forbidden_data_classes"])

    def test_baseline_and_current_collector_audits_are_kept_distinct(self) -> None:
        baseline = self.contract["acp0_0_baseline_audit"]
        current = self.contract["acp0_1_collector_audit"]
        self.assertEqual(
            hashlib.sha256((ROOT / baseline["audit_hook_path"]).read_bytes()).hexdigest(),
            baseline["audit_hook_sha256"],
        )
        self.assertEqual(
            hashlib.sha256((ROOT / current["hooks_manifest_path"]).read_bytes()).hexdigest(),
            current["hooks_manifest_sha256"],
        )
        self.assertEqual(
            hashlib.sha256((ROOT / current["collector_path"]).read_bytes()).hexdigest(),
            current["collector_sha256"],
        )
        self.assertFalse(baseline["audit_hook_acp_privacy_compliant"])
        self.assertTrue(baseline["historical_manifest_contained_frozen_optimizer_hook"])
        self.assertTrue(current["collector_acp_privacy_compliant"])
        self.assertFalse(current["manifest_contains_optimizer_or_rewrite_hook"])
        self.assertTrue(current["manifest_is_acp_collector_ready"])

    def test_coverage_taxonomy_is_exhaustive_and_strong_attribution_is_narrow(self) -> None:
        taxonomy = self.contract["coverage_taxonomy"]
        expected = {
            "observed_and_matched", "observed_not_matched", "transcript_only",
            "unsupported_tool_path", "parse_unknown",
        }
        self.assertEqual(set(taxonomy["states"]), expected)
        self.assertEqual(
            self.contract["measurement_contract"]["strong_attribution_state"],
            "observed_and_matched",
        )
        self.assertTrue(taxonomy["no_extrapolation_beyond_observed_paths"])

    def test_acp0_2_normalizer_artifacts_are_hash_anchored(self) -> None:
        audit = self.contract["acp0_2_normalizer_audit"]
        for path_key, hash_key in (
            ("normalizer_path", "normalizer_sha256"),
            ("replay_path", "replay_sha256"),
            ("normalized_event_schema", "normalized_event_schema_sha256"),
            ("transcript_call_schema", "transcript_call_schema_sha256"),
            ("coverage_ledger_schema", "coverage_ledger_schema_sha256"),
            ("semantic_dictionary", "semantic_dictionary_sha256"),
            ("synthetic_fixture", "synthetic_fixture_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertFalse(audit["derived_waste_or_optimization_metrics"])

    def test_acp0_3_reporter_artifacts_are_hash_anchored_and_fact_only(self) -> None:
        audit = self.contract["acp0_3_reporter_audit"]
        for path_key, hash_key in (
            ("reporter_path", "reporter_sha256"),
            ("fact_report_schema", "fact_report_schema_sha256"),
            ("semantic_dictionary", "semantic_dictionary_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertEqual(audit["report_schema_id"], "fact-report-v1")
        self.assertTrue(audit["fact_only"])
        self.assertFalse(audit["new_correlation"])
        self.assertFalse(audit["cycle_inference"])
        self.assertFalse(audit["derived_waste_or_optimization_metrics"])

    def test_acp0_4_failure_is_hash_anchored_and_not_promoted_to_complete(self) -> None:
        audit = self.contract["acp0_4_no_interference_audit"]
        for path_key, hash_key in (
            ("runner_path", "runner_sha256"),
            ("manifest_path", "manifest_sha256"),
            ("results_path", "results_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertEqual(audit["status"], "failed_cost_neutrality")
        self.assertEqual(audit["pair_count"], 12)
        self.assertEqual(audit["correct_pair_count"], 12)
        self.assertGreater(audit["pooled_total_ratio"], audit["token_ratio_ceiling"])
        self.assertFalse(audit["measurement_foundation_complete"])

    def test_acp0_4a_inconclusive_result_is_hash_anchored_and_not_promoted(self) -> None:
        audit = self.contract["acp0_4a_variance_attribution_audit"]
        for path_key, hash_key in (
            ("runner_path", "runner_sha256"),
            ("results_path", "results_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertEqual(audit["status"], "inconclusive")
        self.assertEqual(audit["run_count"], 120)
        self.assertLessEqual(audit["pooled_total_ratio"], audit["token_ratio_ceiling"])
        self.assertFalse(audit["preregistered_path_signal"])
        self.assertFalse(audit["correctness_zero_regression"])
        self.assertFalse(audit["measurement_foundation_complete"])

    def test_acp0_4b_prospective_closure_is_hash_anchored_and_completes_foundation(self) -> None:
        audit = self.contract["acp0_4b_correctness_closure_audit"]
        for path_key, hash_key in (
            ("spec_path", "spec_sha256"),
            ("native_calibration_path", "native_calibration_sha256"),
            ("runner_path", "runner_sha256"),
            ("results_path", "results_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertEqual(audit["status"], "pass")
        self.assertEqual(audit["case_classification"], "stochastic_diagnostic")
        self.assertGreaterEqual(audit["accuracy_delta_on_minus_off"], audit["minimum_accuracy_delta"])
        self.assertFalse(audit["correctness_runs_enter_cost_or_path_gate"])
        self.assertFalse(audit["prior_results_rewritten"])
        self.assertTrue(audit["measurement_foundation_complete"])

    def test_graduation_certificate_is_scoped_hash_anchored_and_revalidatable(self) -> None:
        certificate = self.contract["acp0_graduation_certificate"]
        digest = hashlib.sha256((ROOT / certificate["certificate_path"]).read_bytes()).hexdigest()
        self.assertEqual(digest, certificate["certificate_sha256"])
        self.assertEqual(certificate["status"], "complete_under_frozen_validation_scope")
        self.assertFalse(certificate["global_zero_interference_claim"])
        self.assertFalse(certificate["statistical_causality_claim"])
        self.assertFalse(certificate["host_binary_cryptographically_frozen"])
        self.assertTrue(certificate["unknown_remains_valid"])
        self.assertTrue(certificate["revalidation_on_host_model_schema_or_online_path_change"])

    def test_post_acp0_roadmap_is_hash_anchored_parallel_and_collector_frozen(self) -> None:
        roadmap = self.contract["post_acp0_roadmap"]
        for path_key, hash_key in (
            ("acp0h_plan_path", "acp0h_plan_sha256"),
            ("acp1_0_plan_path", "acp1_0_plan_sha256"),
            ("acp1_1_plan_path", "acp1_1_plan_sha256"),
            ("acp1_2_plan_path", "acp1_2_plan_sha256"),
            ("acp1_3a_plan_path", "acp1_3a_plan_sha256"),
        ):
            digest = hashlib.sha256((ROOT / roadmap[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, roadmap[hash_key])
        self.assertEqual(roadmap["acp0h_status"], "acp0h_v1_complete")
        self.assertTrue(roadmap["acp0h_v1_is_finite"])
        self.assertTrue(roadmap["acp0h_provenance_and_chain_required_before_first_expensive_acp1_experiment"])
        self.assertEqual(roadmap["acp1_0_status"], "complete_under_frozen_experiment_scope")
        self.assertTrue(roadmap["acp1_0_fact_only"])
        self.assertEqual(roadmap["acp1_1_status"], "complete_under_frozen_experiment_scope")
        self.assertEqual(roadmap["acp1_1_relation_scope"], "within_session")
        self.assertFalse(roadmap["acp1_1_repetition_implies_unnecessary"])
        self.assertEqual(roadmap["acp1_2_status"], "complete_under_frozen_experiment_scope")
        self.assertTrue(roadmap["acp1_2_hypothesis_only"])
        self.assertFalse(roadmap["acp1_2_intervention_executed"])
        self.assertEqual(roadmap["acp1_3a_status"], "complete_under_frozen_experiment_scope")
        self.assertTrue(roadmap["acp1_3a_fact_only"])
        self.assertFalse(roadmap["acp1_3a_intervention_executed"])
        self.assertEqual(roadmap["acp1_3a_new_vs_history_status"], "unknown")
        self.assertTrue(roadmap["collector_remains_frozen"])

    def test_acp0h_provenance_and_chain_are_hash_anchored_privacy_safe_and_offline(self) -> None:
        audit = self.contract["acp0h_provenance_chain_audit"]
        for path_key, hash_key in (
            ("manifest_schema_path", "manifest_schema_sha256"),
            ("manifest_generator_path", "manifest_generator_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertEqual(audit["manifest_schema_id"], "experiment-manifest-v1")
        self.assertTrue(audit["closed_environment_allowlist"])
        self.assertFalse(audit["artifact_paths_persisted"])
        self.assertFalse(audit["raw_environment_persisted"])
        self.assertTrue(audit["deterministic_checksum_chain"])
        self.assertFalse(audit["collector_modified"])

    def test_acp1_contract_and_fixture_are_hash_anchored_fact_only_and_offline(self) -> None:
        audit = self.contract["acp1_0_contract_audit"]
        for path_key, hash_key in (
            ("semantic_dictionary_path", "semantic_dictionary_sha256"),
            ("attribution_schema_path", "attribution_schema_sha256"),
            ("attribution_fixture_path", "attribution_fixture_sha256"),
            ("attribution_engine_path", "attribution_engine_sha256"),
            ("attribution_renderer_path", "attribution_renderer_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertEqual(audit["output_schema_id"], "cost-attribution-baseline-v1")
        self.assertTrue(audit["formulas_frozen_before_engine_output"])
        self.assertTrue(audit["fact_only"])
        self.assertFalse(audit["new_correlation"])
        self.assertFalse(audit["cycle_inference"])
        self.assertFalse(audit["raw_event_input"])
        self.assertTrue(audit["read_only"])
        self.assertTrue(audit["unknown_preserved"])
        self.assertTrue(audit["renderer_source_is_canonical_attribution_json_only"])
        self.assertFalse(audit["renderer_new_metrics"])
        self.assertFalse(audit["renderer_diagnosis"])
        self.assertTrue(audit["no_online_effect"])
        self.assertFalse(audit["collector_modified"])

    def test_acp0h_recalibration_is_hash_anchored_manifest_driven_and_tiered(self) -> None:
        audit = self.contract["acp0h_recalibration_audit"]
        for path_key, hash_key in (
            ("state_schema_path", "state_schema_sha256"),
            ("policy_path", "policy_sha256"),
            ("decision_schema_path", "decision_schema_sha256"),
            ("change_matrix_path", "change_matrix_sha256"),
            ("decision_engine_path", "decision_engine_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertTrue(audit["manifest_derived_state"])
        self.assertEqual(audit["tracked_field_count"], 23)
        self.assertEqual(audit["synthetic_case_count"], 25)
        self.assertEqual(audit["modes"], ["none", "smoke", "full_paired"])
        self.assertTrue(audit["full_paired_includes_smoke"])
        self.assertTrue(audit["unknown_transition_triggers"])
        self.assertFalse(audit["collector_modified"])

    def test_acp0h_benchmark_governance_is_hash_anchored_and_preserves_history(self) -> None:
        audit = self.contract["acp0h_benchmark_governance_audit"]
        for path_key, hash_key in (
            ("registry_schema_path", "registry_schema_sha256"),
            ("registry_path", "registry_sha256"),
            ("validator_path", "validator_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertEqual(audit["case_count"], 12)
        self.assertEqual(audit["active_count"], 11)
        self.assertEqual(audit["diagnostic_only_count"], 1)
        self.assertEqual(audit["stable_gate_count"], 8)
        self.assertEqual(audit["coverage_probe_count"], 2)
        self.assertEqual(audit["failure_injection_count"], 1)
        self.assertEqual(audit["stochastic_diagnostic_count"], 1)
        self.assertEqual(audit["new_stable_minimum_repetitions"], 20)
        self.assertEqual(audit["new_stable_minimum_correct"], 19)
        self.assertEqual(audit["formal_baseline_input_count"], 1)
        self.assertEqual(audit["active_formal_baseline_input_count"], 1)
        self.assertFalse(audit["historical_cases_deleted"])
        self.assertFalse(audit["collector_modified"])

    def test_acp1_frozen_baseline_is_hash_anchored_governed_and_scoped(self) -> None:
        audit = self.contract["acp1_0_frozen_baseline_audit"]
        for path_key, hash_key in (
            ("validation_scope_path", "validation_scope_sha256"),
            ("spec_path", "spec_sha256"),
            ("runner_path", "runner_sha256"),
            ("normalized_result_path", "normalized_result_sha256"),
            ("coverage_ledger_path", "coverage_ledger_sha256"),
            ("fact_report_path", "fact_report_sha256"),
            ("attribution_path", "attribution_sha256"),
            ("markdown_path", "markdown_sha256"),
            ("cli_text_path", "cli_text_sha256"),
            ("calibration_state_path", "calibration_state_sha256"),
            ("baseline_index_path", "baseline_index_sha256"),
            ("experiment_manifest_path", "experiment_manifest_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertEqual(audit["status"], "complete_under_frozen_experiment_scope")
        self.assertEqual(audit["formal_baseline_input_id"], "co1_4_observe_replay")
        self.assertTrue(all(audit[f"g{number}_{suffix}"] for number, suffix in (
            (1, "provenance_complete_with_declared_unknowns"),
            (2, "governance_valid"),
            (3, "end_to_end_determinism"),
            (4, "measurement_integrity"),
            (5, "freeze_integrity"),
        )))
        self.assertEqual(audit["observed_call_count"], 16)
        self.assertEqual(audit["observed_matched_visible_estimated_tokens"], 17651)
        self.assertFalse(audit["raw_private_artifact_produced"])
        self.assertTrue(audit["fact_only"])
        self.assertFalse(audit["global_validity_claim"])
        self.assertFalse(audit["collector_modified"])

    def test_acp1_1_repeated_evidence_is_hash_anchored_scoped_and_fact_only(self) -> None:
        audit = self.contract["acp1_1_repeated_evidence_audit"]
        for path_key, hash_key in (
            ("validation_scope_path", "validation_scope_sha256"),
            ("semantic_dictionary_path", "semantic_dictionary_sha256"),
            ("analysis_schema_path", "analysis_schema_sha256"),
            ("relation_fixture_path", "relation_fixture_sha256"),
            ("engine_path", "engine_sha256"),
            ("renderer_path", "renderer_sha256"),
            ("spec_path", "spec_sha256"),
            ("runner_path", "runner_sha256"),
            ("analysis_path", "analysis_sha256"),
            ("markdown_path", "markdown_sha256"),
            ("cli_text_path", "cli_text_sha256"),
            ("baseline_index_path", "baseline_index_sha256"),
            ("experiment_manifest_path", "experiment_manifest_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertEqual(audit["status"], "complete_under_frozen_experiment_scope")
        self.assertEqual(audit["relation_scope"], "within_session")
        self.assertEqual(audit["within_session_relation_count"], 0)
        self.assertEqual(audit["unique_repeated_observation_tokens"], 0)
        self.assertEqual(audit["acp1_0_cross_session_exact_repeat_volume_preserved"], 5288)
        self.assertEqual(audit["path_identity_coverage_status"], "unknown")
        self.assertEqual(audit["content_stability_status"], "unknown")
        self.assertFalse(audit["multiple_relations_multiply_tokens"])
        self.assertFalse(audit["repetition_implies_unnecessary"])
        self.assertTrue(audit["fact_only"])
        self.assertTrue(audit["no_online_effect"])
        self.assertFalse(audit["collector_modified"])

    def test_acp1_2_hypothesis_catalog_is_hash_anchored_unknown_and_non_causal(self) -> None:
        audit = self.contract["acp1_2_hypothesis_catalog_audit"]
        for path_key, hash_key in (
            ("validation_scope_path", "validation_scope_sha256"),
            ("semantic_dictionary_path", "semantic_dictionary_sha256"),
            ("catalog_schema_path", "catalog_schema_sha256"),
            ("hypothesis_fixture_path", "hypothesis_fixture_sha256"),
            ("generator_path", "generator_sha256"),
            ("renderer_path", "renderer_sha256"),
            ("spec_path", "spec_sha256"),
            ("runner_path", "runner_sha256"),
            ("catalog_path", "catalog_sha256"),
            ("markdown_path", "markdown_sha256"),
            ("cli_text_path", "cli_text_sha256"),
            ("catalog_index_path", "catalog_index_sha256"),
            ("experiment_manifest_path", "experiment_manifest_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertEqual(audit["status"], "complete_under_frozen_experiment_scope")
        self.assertEqual(audit["candidate_count"], 5)
        self.assertEqual(audit["high_cost_call_candidate_count"], 5)
        self.assertEqual(audit["cost_concentration_candidate_count"], 0)
        self.assertEqual(audit["repeated_or_overlapping_evidence_candidate_count"], 0)
        self.assertEqual(audit["unique_target_call_count"], 5)
        self.assertEqual(audit["unique_target_observed_exposure_tokens"], 10735)
        self.assertEqual(audit["unique_target_observed_share"], 0.608180839612)
        self.assertEqual(audit["necessity_status"], "unknown")
        self.assertEqual(audit["causal_status"], "untested")
        self.assertEqual(audit["validation_feasibility"], "blocked")
        self.assertFalse(audit["avoidable_or_savings_estimate_produced"])
        self.assertFalse(audit["intervention_executed"])
        self.assertFalse(audit["agent_recommendation_produced"])
        self.assertTrue(audit["no_online_effect"])
        self.assertFalse(audit["collector_modified"])

    def test_acp1_3a_cycle_cost_is_hash_anchored_exact_linked_and_fact_only(self) -> None:
        audit = self.contract["acp1_3a_cycle_cost_audit"]
        for path_key, hash_key in (
            ("validation_scope_path", "validation_scope_sha256"),
            ("semantic_dictionary_path", "semantic_dictionary_sha256"),
            ("cycle_fixture_path", "cycle_fixture_sha256"),
            ("observations_schema_path", "observations_schema_sha256"),
            ("analysis_schema_path", "analysis_schema_sha256"),
            ("extractor_analyzer_path", "extractor_analyzer_sha256"),
            ("renderer_path", "renderer_sha256"),
            ("spec_path", "spec_sha256"),
            ("runner_path", "runner_sha256"),
            ("observations_path", "observations_sha256"),
            ("analysis_path", "analysis_sha256"),
            ("markdown_path", "markdown_sha256"),
            ("cli_text_path", "cli_text_sha256"),
            ("baseline_index_path", "baseline_index_sha256"),
            ("experiment_manifest_path", "experiment_manifest_sha256"),
        ):
            digest = hashlib.sha256((ROOT / audit[path_key]).read_bytes()).hexdigest()
            self.assertEqual(digest, audit[hash_key])
        self.assertEqual(audit["status"], "complete_under_frozen_experiment_scope")
        self.assertEqual(audit["source_run_count"], 120)
        self.assertEqual(audit["exact_linked_run_count"], 120)
        self.assertEqual(audit["usage_snapshot_count"], 287)
        self.assertEqual(audit["off_run_count"], 60)
        self.assertEqual(audit["on_run_count"], 60)
        self.assertEqual(audit["cycle_four_sample_status"], "insufficient_descriptive_sample")
        self.assertEqual(audit["new_vs_history_status"], "unknown")
        self.assertEqual(audit["counterfactual_cycle_cost_status"], "unknown")
        self.assertTrue(audit["fact_only"])
        self.assertFalse(audit["causal_claim_produced"])
        self.assertFalse(audit["waste_or_savings_estimate_produced"])
        self.assertFalse(audit["intervention_executed"])
        self.assertTrue(audit["no_online_effect"])
        self.assertFalse(audit["collector_modified"])

    def test_fixture_source_hash_and_privacy_flags(self) -> None:
        source = RESOURCES / "co1_4_observe_results.json"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(digest, self.fixture["source"]["sha256"])
        self.assertTrue(all(value is False for value in self.fixture["privacy"].values() if isinstance(value, bool)))
        serialized = json.dumps(self.fixture, ensure_ascii=False)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("tool_response", serialized)
        self.assertTrue(
            set(self.fixture["event_columns"]).isdisjoint(
                {"command", "prompt", "response", "transcript", "absolute_path"}
            )
        )

    def test_replay_fixture_reproduces_frozen_co1_4_baseline(self) -> None:
        columns = self.fixture["event_columns"]
        events = [dict(zip(columns, row, strict=True)) for row in self.fixture["events"]]
        expected = self.fixture["expected"]
        self.assertEqual(len(events), expected["event_count"])
        self.assertEqual(len({event["session_id_hash"] for event in events}), expected["session_count"])
        for event in events:
            self.assertEqual(len(event["session_id_hash"]), 64)
            self.assertEqual(len(event["event_id"]), 64)
            self.assertEqual(len(event["output_sha256"]), 64)
            self.assertEqual(event["estimated_raw_tokens"], (event["raw_chars"] + 3) // 4)
        self.assertEqual(sum(event["raw_chars"] for event in events), expected["raw_chars"])
        self.assertEqual(sum(event["estimated_raw_tokens"] for event in events), expected["estimated_raw_tokens"])
        self.assertEqual(sum(event["model_visible_chars"] for event in events), expected["model_visible_chars"])
        self.assertEqual(
            sum(event["estimated_model_visible_tokens"] for event in events),
            expected["estimated_model_visible_tokens"],
        )
        duplicate_count = sum(count - 1 for count in Counter(event["output_sha256"] for event in events).values())
        self.assertEqual(duplicate_count, expected["exact_payload_duplicate_count"])
        self.assertEqual(dict(Counter(event["command_shape"] for event in events)), expected["command_shape_counts"])


if __name__ == "__main__":
    unittest.main()
