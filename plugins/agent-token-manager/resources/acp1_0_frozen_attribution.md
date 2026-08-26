# ACP Cost Attribution Map

- Schema: `cost-attribution-baseline-v1`
- Engine: `acp-attributor-v0.1`
- Renderer: `acp-attribution-renderer-v0.1`
- Attribution input SHA-256: `f71ca615902b9e2ed6cd31644d89a89eff188fa1758ad377d285756331419973`
- Source fact report SHA-256: `65bdcac9f6cc53053bac8b848283600b4c2f1846bdeabca7f3f5b8c979001291`

## Session Summary

- Observed calls: 16 [complete]
- Attributed visible estimated tokens: 17651 [complete]
- Unknown visible estimated tokens: 0
- Eligible calls: 16
- Attribution coverage status: complete
- Session total tokens: unknown [unknown]
- Model cycles: unknown [unknown]

### Sessions

| Session ID | Observed events | Denominator tokens | Attributed tokens | Unattributed tokens | Coverage | Status |
|---|---:|---:|---:|---:|---:|---|
| `092cfcf226321aaca4f767440f8d3ee1247282b3fdf8d747bb1eb66f2661b067` | 1 | 2455 | 2455 | 0 | 1.0 | complete |
| `1ef9dda4b5b8cfa4c8f602852976170b932fc9c4ee36ce1db62864594fbed643` | 1 | 366 | 366 | 0 | 1.0 | complete |
| `249cd9062c9dd56f5507de6d8eedc2f7a109e45052d50b04ecd9af2a8a3bec17` | 2 | 2644 | 2644 | 0 | 1.0 | complete |
| `3734b902ff8ec68cddb2145414587c456d7923b823c0cfb98abe22d575ac9663` | 1 | 2086 | 2086 | 0 | 1.0 | complete |
| `7ced56bd195d7a76b951099b4a1c244e63c30011d9db404d4706875691b7e08a` | 2 | 529 | 529 | 0 | 1.0 | complete |
| `8489dfa1760ec77cd9f1e4cc0d75faa92c25952090309fc9e22b8207e98a513f` | 1 | 449 | 449 | 0 | 1.0 | complete |
| `8624c02f276f7c0e704187b6f5aeb51f59c9a832c43ec9549f41eb847633cf9c` | 1 | 1896 | 1896 | 0 | 1.0 | complete |
| `86830b662c40ac1803cc747a91ce78d1ef5e69c0bd7cdb97a1758ecb31cc166a` | 2 | 2644 | 2644 | 0 | 1.0 | complete |
| `8c73962890c48a3b7fb1b50e5d6ae1f6100ed4a535c9259b73a16e3cac941b67` | 1 | 337 | 337 | 0 | 1.0 | complete |
| `b32550a685690c9e26a2b9de70745711855f60f4970eab72c2f66cc5026db962` | 1 | 1756 | 1756 | 0 | 1.0 | complete |
| `cc27c469a4b41bbaaeb63d21998a3503e09320411e6e68a9a5080a0779174775` | 2 | 2413 | 2413 | 0 | 1.0 | complete |
| `e81050dab83b0e5dace7f902a8bda3b2343e8f20ba739486437cc85680bf19aa` | 1 | 76 | 76 | 0 | 1.0 | complete |

## Cost Concentration

| Measure | Value | Status |
|---|---:|---|
| Top-1 share | 0.139085604215 | complete |
| Top-3 share | 0.374596340151 | complete |
| Top-10 share | 0.907710611297 | complete |
| Top 10% share | 0.257265877287 | complete |
| Top 20% share | 0.491926803014 | complete |
| Call HHI | 0.100553287061 | complete |
| Tool-family HHI | 1.0 | complete |

## Tool-family Map

| Tool family | Calls | Visible tokens | Share | Median | p90 | Max | Status |
|---|---:|---:|---:|---:|---:|---:|---|
| bash | 16 | 17651 | 1.0 | 573.0 | 2086 | 2455 | complete |

## Top Calls

| Rank | Call index | Stable call ID | Tool family | Visible tokens | Share |
|---:|---:|---|---|---:|---:|
| 1 | 0 | `f38b46c71e831aa94322206135a0e6c3b4975239d3e5f3b8d076c33dba1cf0fd` | bash | 2455 | 0.139085604215 |
| 2 | 0 | `6fee2f2cdd7fb881d750bbab33f83bc8a8e2305659ffea1d6a8e80b4c60f4b85` | bash | 2086 | 0.118180273072 |
| 3 | 0 | `87b10ee8c1130ba5661b95573ffba470eeae12a35259104934faf2748ad87dfc` | bash | 2071 | 0.117330462863 |
| 4 | 0 | `b00805c90d6aaf46054e03a0096ffa3da58d50a343f3629fc67821dfdc1c1c30` | bash | 2071 | 0.117330462863 |
| 5 | 0 | `20a3be8874668f11767d57a3d316dd8d2e4748727e2c75862c1a7f675ed5fac7` | bash | 2052 | 0.116254036598 |
| 6 | 0 | `3f02c36ac2795750903a07cf5800d23ef8fb4c4d14e59a327ac717bcaf313c26` | bash | 1896 | 0.107416010424 |
| 7 | 0 | `6913075bf901d59510aa015c423d70b9e489f332d017cc8cf849f16abffbd93e` | bash | 1756 | 0.099484448473 |
| 8 | 1 | `a00bbf53e55b6c823fcd40a1312f7f8d071268285682b3ed619756114f689c5f` | bash | 573 | 0.032462749986 |
| 9 | 1 | `82e100a693d764b9b5420b2b96996ac148f1d6cb8a92a1c758b541efdc69d577` | bash | 573 | 0.032462749986 |
| 10 | 1 | `d882654095c0a049c15a770753d0b088f7ea2394ba6fde47ff2ae06c56fd07ee` | bash | 489 | 0.027703812815 |

## Repetition Facts

Factual relationships only; no necessity or actionability conclusion is made.

| Relationship | Status | Relation count | Listed observations | Known observations | Group observation visible tokens |
|---|---|---:|---:|---:|---:|
| Exact repeated evidence | complete | 2 | 4 | 4 | 5288 |
| Same-file repeated evidence | unknown | 0 | 0 | 0 | unknown |
| Range-overlap evidence | unknown | 0 | 0 | 0 | unknown |

## Coverage / Unknown

- Status: complete
- Unknown observations: 0
- Unknown visible estimated tokens: 0

| Unknown reason | Count |
|---|---:|

### Non-complete Call Evidence

| Stable call ID | Tool family | Coverage state | Attributed tokens | Unattributed tokens | Status |
|---|---|---|---:|---:|---|

## Traceability

| Output metric path | Canonical source pointer(s) |
|---|---|
| `/scope_and_denominators/observed_calls` | `/layers/observed_tool_result_cost/tool_result_count` |
| `/scope_and_denominators/observed_matched_model_visible_estimated_tokens` | `/layers/model_visible_tool_context/estimated_model_visible_tokens` |
| `/coverage_summary` | `/drilldowns/evidence_coverage` |
| `/session_attribution` | `/drilldowns/sessions` |
| `/tool_family_attribution` | `/drilldowns/tool_families` |
| `/call_attribution` | `/drilldowns/tool_calls` |
| `/top_calls_and_concentration` | `/drilldowns/tool_calls` |
| `/objective_repetition_facts` | `/duplicate_facts` |
| `/unknown_volume_and_reasons` | `/drilldowns/evidence_coverage/unknown` |
