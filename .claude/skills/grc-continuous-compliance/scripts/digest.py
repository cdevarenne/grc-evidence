"""Small, stable digests of the bundle and of a scan: the only input the LLM step sees."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from okf_lib import Bundle

Json = dict[str, Any]
MESSAGE_CHARS = 160


def bundle_digest(bundle: Bundle) -> Json:
    """Per control: title, one-line description, and intent. Stable across runs, so it is the cached prefix."""
    return {
        c.key: {"title": c.title, "description": c.description, "intent": bundle.section(c, "Intent") or ""}
        for c in bundle.controls()
    }


def scan_digest(mapping: Json) -> Json:
    """Per control: status and counts. Per coverage-gap rule: tool, rule_id, first message line, count."""
    controls = {
        key: {
            "status": entry["status"],
            "findings": len(entry["findings"]),
            "by_severity": dict(sorted(Counter(f["severity"] for f in entry["findings"]).items())),
        }
        for key, entry in sorted(mapping["controls"].items())
    }
    gaps: dict[tuple[str, str], Json] = {}
    for u in mapping["unmapped"]:
        f = u["finding"]
        gap = gaps.setdefault(
            (f["tool"], f["rule_id"]),
            {"tool": f["tool"], "rule_id": f["rule_id"], "message": f["message"].splitlines()[0][:MESSAGE_CHARS],
             "reason": u["reason"], "count": 0},
        )
        gap["count"] += 1
    return {"controls": controls, "gaps": [gaps[k] for k in sorted(gaps)]}


def dumps(doc: Json) -> str:
    """Canonical JSON (sorted keys, no whitespace variance) so identical input hashes identically."""
    return json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=False)
