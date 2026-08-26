"""Public-archive pytest policy.

The excluded checks reconstruct private inventories or historical subject commits.
Those inputs are intentionally absent from the publishable repository.  Keeping the
node IDs explicit prevents an environment-dependent failure from being mistaken for
a product regression while leaving every archived test visible for audit.
"""

from __future__ import annotations

import pytest


ARCHIVAL_ONLY_TESTS = {
    "tests/test_acp1_3a_frozen_baseline.py::Acp13aFrozenBaselineTests::test_private_source_reextracts_and_outputs_reproduce_byte_for_byte",
    "tests/test_acp1_3b_frozen_feasibility.py::Acp13bFrozenFeasibilityTests::test_manifest_binds_public_index_and_private_inventory",
    "tests/test_acp1_3b_frozen_feasibility.py::Acp13bFrozenFeasibilityTests::test_private_chain_reconstructs_without_persisting_path",
    "tests/test_acp1_3c_frozen_registry.py::Acp13cFrozenRegistryTests::test_manifest_and_index_bind_every_artifact",
    "tests/test_acp1_3c_frozen_registry.py::Acp13cFrozenRegistryTests::test_private_inventory_reconstructs_without_path_disclosure",
    "tests/test_acp1_3d_frozen_ablation.py::Acp13dFrozenAblationTests::test_manifest_and_index_bind_every_artifact",
    "tests/test_acp1_3d_frozen_ablation.py::Acp13dFrozenAblationTests::test_private_inventory_reconstructs_without_path_disclosure",
    "tests/test_acp1_4_frozen_generalization.py::Acp14FrozenGeneralizationTests::test_private_inventory_reconstructs_eighty_four_valid_runs",
    "tests/test_acp1_4_generalization.py::Acp14GeneralizationTests::test_all_treatments_are_deterministic_and_change_subject",
    "tests/test_acp1_4_generalization.py::Acp14GeneralizationTests::test_bash_subset_treatments_remain_valid_python_and_remove_methods",
    "tests/test_acp1_4_generalization.py::Acp14GeneralizationTests::test_read_treatments_preserve_ground_truth_lines",
    "tests/test_acp1_4_generalization.py::Acp14GeneralizationTests::test_search_treatments_preserve_target_and_reduce_other_matches",
    "tests/test_acp1_4c_bash_requalification.py::Acp14cBashRequalificationTests::test_control_commands_succeed_without_writes",
    "tests/test_acp1_4c_bash_requalification.py::Acp14cBashRequalificationTests::test_treatments_are_deterministic_preserve_answer_and_activate",
    "tests/test_acp1_4c_frozen_requalification.py::Acp14cFrozenRequalificationTests::test_private_inventory_reconstructs_one_hundred_ninety_four_runs",
    "tests/test_acp1_4d_activation_audit.py::Acp14dActivationAuditTests::test_audit_is_deterministic_from_frozen_private_subset",
    "tests/test_acp1_4d_activation_audit.py::Acp14dActivationAuditTests::test_private_inventory_binds_exactly_sixty_runs",
    "tests/test_acp1_4e_frozen_v2_validation.py::Acp14eFrozenV2ValidationTests::test_private_inventory_binds_ninety_six_runs",
    "tests/test_acp1_4e_v2_validation.py::Acp14eV2ValidationTests::test_treatments_are_deterministic_and_preserve_answer_evidence",
    "tests/test_acp1_4f_f1_early_stop.py::Acp14fF1EarlyStopTests::test_private_completed_inventory_reconstructs_exactly",
    "tests/test_acp1_4f_r_audit.py::Acp14fRAuditTests::test_checked_in_result_is_reproducible",
    "tests/test_acp_cycle_cost.py::AcpCycleCostTests::test_frozen_private_source_extracts_120_exact_links_without_private_bodies",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    archival = pytest.mark.skip(
        reason="requires private experiment inventories or historical source commits not published in this archive"
    )
    for item in items:
        if item.nodeid in ARCHIVAL_ONLY_TESTS:
            item.add_marker(archival)
