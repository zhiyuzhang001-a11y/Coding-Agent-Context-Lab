---
name: budgeted-code-reading
description: Navigates repositories with persistent task state, feedback-ranked sparse markers, duplicate suppression, and hard-budget source expansion. Use when understanding code, locating implementations, tracing relevant functions, or answering repository questions without loading complete files unnecessarily.
---

# Budgeted Code Reading

Use the persistent Task Navigator for natural-language or cross-file exploration so feedback, duplicate evidence and the remaining budget survive tool calls. If the exact file and symbols are already known, skip task navigation and route the file directly. Results expose ranking reasons, line numbers, omissions, estimated tokens, route reason and cache status.

## Workflow

1. When the location is unknown, incrementally refresh the map and start one budgeted task:

   ```bash
   /usr/bin/env python3 "$PLUGIN_ROOT/scripts/navigation_map.py" index "$PWD"
   /usr/bin/env python3 "$PLUGIN_ROOT/scripts/task_navigator.py" start "$PWD" \
     --task "fix ranking behavior" --total-budget 3000 \
     --navigation-budget 800 --expansion-budget 2200
   ```

2. Call `next`, then expand its Marker. After inspecting evidence, send concise structured feedback; stop explicitly when evidence is sufficient or expected gain is low:

   ```bash
   /usr/bin/env python3 "$PLUGIN_ROOT/scripts/task_navigator.py" next "$PWD" --task-id TASK_ID
   /usr/bin/env python3 "$PLUGIN_ROOT/scripts/task_navigator.py" expand "$PWD" \
     --task-id TASK_ID --marker-id MARKER_ID --budget 800
   /usr/bin/env python3 "$PLUGIN_ROOT/scripts/task_navigator.py" feedback "$PWD" \
     --task-id TASK_ID --marker-id MARKER_ID --relevance relevant \
     --information-gain high --new-symbol discovered_call
   /usr/bin/env python3 "$PLUGIN_ROOT/scripts/task_navigator.py" stop "$PWD" \
     --task-id TASK_ID --reason evidence_sufficient --evidence MARKER_ID
   ```

   Do not repeat an untruncated evidence key. Let the Navigator re-open it only after a hash change, an earlier truncation, or explicit `--force`.

   After two consecutive candidates are marked irrelevant, the Navigator may run one bounded local text rescue before selecting the next Marker. The rescue returns Marker metadata and matching terms, never source bodies, and consumes the same navigation/total budget. To inspect it explicitly, run `task_navigator.py discover ... --source bounded-text --budget 400`; do not repeat an identical discovery query.

3. If the file is known but symbols are unknown, provide the task query. Only use an outline when neither symbols nor a useful query are known:

   ```bash
   /usr/bin/env python3 "$PLUGIN_ROOT/scripts/context_router.py" path/to/file \
     --query "behavior dependency" --budget 800
   ```

4. Do not request a complete symbol again. Batch exact symbols by file. Use narrow search only if the structural map has no useful candidate.

5. Inspect map ranking components plus `route`, `cache_status`, `truncated`, and `omitted_region_count`. Increase the budget only when missing context affects the task. Before editing, obtain the complete target region and necessary surrounding code.

## Budget guidance

- 300–500: structure or one compact symbol.
- 600–1,000: one substantial function.
- 1,000–1,500: several named symbols in one call.

Reserve roughly 300–500 tokens for navigation candidates and the remainder for evidence. The map stores paths, signatures, structural relationships and hashes—not source bodies. Its Python provider understands containment, imports, inheritance, direct calls and selected high-value references. M2d can use bounded local source-region term evidence as a rescue, but embedding, full type inference and data flow remain later experiments.

Treat token estimates as approximate. The cache uses plugin data when available and a private temporary directory otherwise. It stores structure metadata and content hashes, not source bodies; a changed hash causes a miss.

## Fallbacks

- For non-code or low-confidence parsing, use narrow line ranges or a purpose-built parser.
- If map storage is not writable or the language is unsupported, route a known file directly and use narrow search for discovery.
- Never rely on omitted lines for correctness, security, or edits.
