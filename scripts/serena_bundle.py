"""Pure helpers for building a budgeted Serena context bundle."""

from __future__ import annotations

import json
from typing import Any


TOKEN_METHOD = "chars_div_4_v1"


def estimate_tokens(text: str) -> int:
    return (len(text) + 3) // 4


def parse_backend_result(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def preview(value: Any, max_chars: int) -> dict[str, Any]:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) <= max_chars:
        return {"truncated": False, "value": value}
    return {"truncated": True, "preview": serialized[:max_chars] + "…"}


def build_bundle(target_text: str, references_text: str | None, budget_tokens: int, backend_calls: int) -> dict[str, Any]:
    target = parse_backend_result(target_text)
    references = parse_backend_result(references_text) if references_text is not None else None
    limit = budget_tokens * 4
    bundle: dict[str, Any] = {
        "schema_version": 1,
        "backend": "serena",
        "backend_calls": backend_calls,
        "target": target,
        "references": references,
        "truncated": False,
        "estimated_output_tokens": 0,
        "token_count_method": TOKEN_METHOD,
    }
    for _ in range(4):
        serialized = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
        bundle["estimated_output_tokens"] = estimate_tokens(serialized)
        if len(serialized) <= limit:
            return bundle
        bundle["truncated"] = True
        if not isinstance(bundle["references"], dict) or "preview" not in bundle["references"]:
            bundle["references"] = preview(references, max(128, limit // 4))
            continue
        if not isinstance(bundle["target"], dict) or "preview" not in bundle["target"]:
            bundle["target"] = preview(target, max(256, limit // 2))
            continue
        break
    bundle["estimated_output_tokens"] = estimate_tokens(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")))
    return bundle
