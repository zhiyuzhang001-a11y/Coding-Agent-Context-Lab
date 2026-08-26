# Host-Reported Model-Cycle Cost Baseline

- Schema: `model-cycle-cost-analysis-v1`
- Analyzer: `acp-cycle-cost-v0.1`
- Renderer: `acp-cycle-cost-renderer-v0.1`
- Coverage: `complete` (120/120 exact-linked runs)
- Interpretation: descriptive host usage facts; no causal, waste, necessity, or savings verdict

## OFF — primary_native_analysis

### Cycle count and session total

| Cycles | Runs | Sample status | Median total Tokens | Mean total Tokens |
|---:|---:|---|---:|---:|
| 2 | 38 | sufficient_descriptive_sample | 31317.5 | 31645.9210526 |
| 3 | 21 | sufficient_descriptive_sample | 49151 | 51015.1904762 |
| 4 | 1 | insufficient_descriptive_sample | 84033 | 84033 |

### Cycle ordinal cost

| Ordinal | Runs | Sample status | Increment median | Increment mean | Cumulative median |
|---:|---:|---|---:|---:|---:|
| 1 | 60 | sufficient_descriptive_sample | 15549 | 15548.65 | 15549 |
| 2 | 60 | sufficient_descriptive_sample | 15958.5 | 16712.15 | 31505.5 |
| 3 | 22 | sufficient_descriptive_sample | 16969.5 | 18145.7727273 | 49152.5 |
| 4 | 1 | insufficient_descriptive_sample | 23042 | 23042 | 84033 |

### Within-run adjacent increments

| Transition | Runs | Sample status | Median delta | Median ratio |
|---|---:|---|---:|---:|
| 1→2 | 60 | sufficient_descriptive_sample | 403.5 | 1.02593789142 |
| 2→3 | 22 | sufficient_descriptive_sample | 376.5 | 1.02007621214 |
| 3→4 | 1 | insufficient_descriptive_sample | 96 | 1.00418373573 |

## ON — independent_replication

### Cycle count and session total

| Cycles | Runs | Sample status | Median total Tokens | Mean total Tokens |
|---:|---:|---|---:|---:|
| 2 | 37 | sufficient_descriptive_sample | 31267 | 31533.7027027 |
| 3 | 22 | sufficient_descriptive_sample | 49223.5 | 51063.7727273 |
| 4 | 1 | insufficient_descriptive_sample | 84276 | 84276 |

### Cycle ordinal cost

| Ordinal | Runs | Sample status | Increment median | Increment mean | Cumulative median |
|---:|---:|---|---:|---:|---:|
| 1 | 60 | sufficient_descriptive_sample | 15556 | 15553.3 | 15556 |
| 2 | 60 | sufficient_descriptive_sample | 15955 | 16671.0666667 | 31516 |
| 3 | 23 | sufficient_descriptive_sample | 17043 | 18165.7391304 | 49229 |
| 4 | 1 | insufficient_descriptive_sample | 23152 | 23152 | 84276 |

### Within-run adjacent increments

| Transition | Runs | Sample status | Median delta | Median ratio |
|---|---:|---|---:|---:|
| 1→2 | 60 | sufficient_descriptive_sample | 403 | 1.0259280582 |
| 2→3 | 23 | sufficient_descriptive_sample | 385 | 1.02240027083 |
| 3→4 | 1 | insufficient_descriptive_sample | 96 | 1.00416377516 |

## Unknowns

- `new_content_tokens`: `unknown`
- `historical_context_tokens`: `unknown`
- `semantic_history_reprocessing`: `unknown`
- `counterfactual_added_cycle_cost`: `unknown`
- `necessity`: `unknown`
- `avoidability`: `unknown`
