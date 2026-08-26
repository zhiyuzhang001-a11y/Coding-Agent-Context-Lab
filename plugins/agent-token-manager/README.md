# Agent Token Manager plugin

This optional Codex plugin exposes two maintenance-mode research capabilities:

- `budgeted-code-reading`: sparse, budgeted source navigation with persistent task state;
- `context-cost-audit`: a privacy-limited summary of observed tool-result payloads.

The PostToolUse Hook is observe-only. It does not replace tool results and does not claim exact provider usage, hidden Host context, billing cost, or end-to-end savings.

Install it from the repository marketplace:

```bash
codex plugin marketplace add zhiyuzhang001-a11y/Coding-Agent-Context-Lab --ref main
codex plugin add agent-token-manager@coding-agent-context-lab
```

Start a new Codex task after installation. Full usage and interpretation boundaries are documented in the repository root at `docs/USAGE.md`.
