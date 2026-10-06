"""Small, stable digests of the bundle and of a scan: the only input the LLM step sees."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from grc_evidence.okf_lib import FRAMEWORK_SCOPES, Bundle

Json = dict[str, Any]
MESSAGE_CHARS = 160
MAX_TARGETS = 5


def bundle_digest(bundle: Bundle, scoped: bool = False) -> Json:
    """Per control: title, one-line description, and intent. Stable across runs, so it is the cached prefix.

    `scoped=True` adds the framework's component scope (AI-governance controls cover AI components only).
    """
    digest = {}
    for c in bundle.controls():
        entry = {"title": c.title, "description": c.description, "intent": bundle.section(c, "Intent") or ""}
        if scoped:
            entry["scope"] = FRAMEWORK_SCOPES[c.framework]
        digest[c.key] = entry
    return digest


def scan_digest(mapping: Json, targets: bool = False) -> Json:
    """Per control: status and open-finding counts. Per coverage-gap rule: tool, rule_id, first message line, count.

    Accepted risks and suppressed false positives are counted apart, never as open findings (Spec C).

    `targets=True` adds up to MAX_TARGETS files each gap rule fired on, so triage can see where it was found.
    """
    controls = {}
    for key, entry in sorted(mapping["controls"].items()):
        open_findings = [f for f in entry["findings"] if not f.get("accepted")]
        controls[key] = {
            "status": entry["status"],
            "findings": len(open_findings),
            "by_severity": dict(sorted(Counter(f["severity"] for f in open_findings).items())),
        }
        if accepted := len(entry["findings"]) - len(open_findings):
            controls[key]["accepted_risks"] = accepted  # only when present, so earlier digests are unchanged
    gaps: dict[tuple[str, str], Json] = {}
    for u in mapping["unmapped"]:
        f = u["finding"]
        gap = gaps.setdefault(
            (f["tool"], f["rule_id"]),
            {"tool": f["tool"], "rule_id": f["rule_id"], "message": f["message"].splitlines()[0][:MESSAGE_CHARS],
             "reason": u["reason"], "count": 0},
        )
        gap["count"] += 1
        if targets:
            gap.setdefault("targets", set()).add(f["target"])
    for gap in gaps.values():
        if targets:
            gap["targets"] = sorted(gap["targets"])[:MAX_TARGETS]
    digest = {"controls": controls, "gaps": [gaps[k] for k in sorted(gaps)]}
    if false_positives := sum(x["kind"] == "false-positive" for x in mapping.get("suppressed", [])):
        digest["suppressed_false_positives"] = false_positives
    return digest


def dumps(doc: Json) -> str:
    """Canonical JSON (sorted keys, no whitespace variance) so identical input hashes identically."""
    return json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=False)
