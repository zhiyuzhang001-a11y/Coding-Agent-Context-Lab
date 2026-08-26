# ACP Repeated Evidence Map

- Schema: `repeated-evidence-analysis-v1`
- Engine: `acp-repeated-evidence-v0.1`
- Renderer: `acp-repeated-evidence-renderer-v0.1`
- Analysis SHA-256: `dcd1722c782849cf5c9dfb6f8d15555a70b5de99f387ac70fc5ee455ad956c13`
- Relation scope: `within_session`
- Interpretation: repeated observations are factual relations only; no necessity or actionability conclusion is made.

## Observation Volume

- Eligible observed visible estimated tokens: 17651
- Relations: 0
- Unique repeated observations: 0
- Unique repeated observation tokens: 0
- Repeated observation share: 0.0
- Counting rule: each eligible later call counted once regardless of relation multiplicity

## Coverage

| Dimension | Known calls | Status |
|---|---:|---|
| Relation order | 16 | complete |
| Path identity | 0 | unknown |
| Explicit range | 0 | unknown |
| Model cycle | unknown | unknown |

## Relation Facts

| Relation type | Count | Coverage/status |
|---|---:|---|
| Exact payload repeat | 0 | complete |
| Same path repeat | 0 | unknown |
| Exact range repeat | 0 | unknown |
| Range contains | 0 | unknown |
| Range overlap | 0 | unknown |

## Unique Repeated Observations

| Session | Call index | Call ID | Tokens | Relations | Types | Counted once |
|---|---:|---|---:|---:|---|---|

## Call Relations

| Type | Earlier | Later | Basis | Payload equal | Content stability | Cross-cycle |
|---|---|---|---|---|---|---|

## Unknowns

- Source noneligible calls: 0
- Relation-order excluded calls: 0
- Path identity unknown calls: 16
- Explicit range unknown calls: 16
- Cycle relation state: unknown
- Content stability state: unknown

## Traceability

- `/call_relations` ← normalized_batch:/events
- `/unique_repeated_observations` ← normalized_batch:/events, attribution:/call_attribution
- `/observation_volume` ← attribution:/scope_and_denominators/observed_matched_model_visible_estimated_tokens
- `/unknowns` ← coverage_ledger:/unknown, normalized_batch:/events
