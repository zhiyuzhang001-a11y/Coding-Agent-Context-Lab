# ACP Cost Necessity Hypothesis Catalog

- Schema: `cost-necessity-hypothesis-catalog-v1`
- Generator: `acp-hypothesis-catalog-v0.1`
- Renderer: `acp-hypothesis-renderer-v0.1`
- Catalog SHA-256: `74ad21ff2d4a51e749a4ac463310cb2fe8be5f7ee4cbf88fd2cdf9112622032b`
- Status: `candidates_present`
- Meaning: entries are offline experiment candidates, not anomaly, necessity, or actionability conclusions.

## Frozen Candidate Policy

- High-cost minimum share: 0.1
- High-cost minimum observed exposure: 1000
- High-cost candidate cap: 5
- Concentration minimum call HHI: 0.18
- Concentration minimum Top-3 share: 0.6

## Candidate Summary

- Candidate count: 5
- Unique target calls: 5
- Unique target observed exposure tokens: 10735
- Unique target observed share: 0.608180839612
- Counting rule: each target call counted once across overlapping candidates

## Hypothesis Candidates

| ID | Type | Targets | Observed exposure | Share | Necessity | Causal | Feasibility |
|---|---|---:|---:|---:|---|---|---|
| `d4ae627d5b0f9c9b0daf8421c5413de694e6e7db92ef990e077d9b9cb7cfaa28` | high_cost_call_candidate | 1 | 2455 | 0.139085604215 | unknown | untested | blocked |
| `94cf395b031662c2c6d3757f861b3b4ba6958da3a6206d670eabfb2e1b25f750` | high_cost_call_candidate | 1 | 2086 | 0.118180273072 | unknown | untested | blocked |
| `e558b58a2af48cac68e8e78c94b2a5bf84e9113f702bee2e1d7193bc603c056a` | high_cost_call_candidate | 1 | 2071 | 0.117330462863 | unknown | untested | blocked |
| `ed2903454e6294722683bfd7b1f44258fbd87141896873905b9aafd976db9239` | high_cost_call_candidate | 1 | 2071 | 0.117330462863 | unknown | untested | blocked |
| `0a2b2c228383da44afcaff9c0a5ad34de0330a573aef32a368abb1c96edddbe7` | high_cost_call_candidate | 1 | 2052 | 0.116254036598 | unknown | untested | blocked |

## Required Validation

- `construct_isolated_paired_task_replay`
- `apply_controlled_evidence_intervention_in_experimental_harness`
- `compare_correctness`
- `compare_tool_path_and_model_cycles`
- `estimate_delta_only_if_correctness_is_preserved`

## Unknowns and Blocking Conditions

- Necessity status: unknown
- Causal status: untested
- Validation feasibility: blocked
- Blocking reasons: missing_controlled_intervention_interface, missing_replayable_task_context

## Traceability

- `/hypothesis_candidates` ← attribution:/call_attribution, attribution:/top_calls_and_concentration, repeated_evidence:/unique_repeated_observations
- `/candidate_summary` ← attribution:/scope_and_denominators/observed_matched_model_visible_estimated_tokens, attribution:/call_attribution
- `/unknowns` ← attribution:/coverage_summary, repeated_evidence:/unknowns
