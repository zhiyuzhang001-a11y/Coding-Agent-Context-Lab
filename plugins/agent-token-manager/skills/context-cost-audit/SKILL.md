---
name: context-cost-audit
description: Summarize the Agent Token Manager observe-only tool-result audit when the user asks where tool-output context went, which tools returned the largest payloads, or whether results repeated. Do not use it to claim exact provider billing, hidden Host context, or causal token savings.
---

# Context Cost Audit

Report only aggregate facts from the installed plugin's private audit log.

1. Require both `PLUGIN_ROOT` and `PLUGIN_DATA`. If either is unavailable, say the plugin data location is unavailable in this environment. Do not search the user's home directory for logs.
2. If `$PLUGIN_DATA/tool-output-audit.jsonl` does not exist or contains no records, report that no observed tool-result records are available.
3. Otherwise run:

   ```bash
   python3 "$PLUGIN_ROOT/scripts/report_audit.py" \
     "$PLUGIN_DATA/tool-output-audit.jsonl" --json
   ```

4. Summarize the largest tool categories, read-result share, repeated identical results, and large-read candidates. Do not reveal raw log lines, paths, hashes, commands, prompts, or result bodies.
5. Always label `estimated_response_tokens` as a `characters / 4` payload estimate. It is not provider usage, complete context occupancy, billing truth, or evidence that an intervention would reduce total task cost.

If the user asks for exact Token attribution, explain that the Hook does not expose every Host-injected or server-side context category and therefore cannot provide that claim.
