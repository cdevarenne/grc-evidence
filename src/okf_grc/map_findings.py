"""Join normalized findings to in-bundle controls; never invent a mapping."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from okf_grc.okf_lib import EXPIRY_WARNING_DAYS, GUARDRAIL_TYPES, SCANNER_TYPE, Bundle, Suppression, applies, load_bundle

Finding = dict[str, Any]
CONTEXT_FIELDS = ("risk_tier",)  # inventory fields that `applies_when` may name
RISK_TIERS = ("minimal", "limited", "high")  # EU AI Act risk classes the inventory may declare


def _controls_for(bundle: Bundle, finding: Finding) -> tuple[list[str], str | None]:
    """Control keys a finding maps to, or ([], reason) when it is a coverage gap."""
    declaring = bundle.by_rule(finding["tool"], finding["rule_id"])
    if not declaring:
        return [], "no-rule-match"
    keys = sorted({k for c in declaring for k in c.control_keys if bundle.control(k)})
    return (keys, None) if keys else ([], "control-not-in-bundle")


def _evidence(bundle: Bundle, key: str) -> tuple[list[str], list[str]]:
    """(evidenced_by, satisfied_by) for a control, derived only from `rule_ids` declarations."""
    declaring = bundle.declaring(key)
    tools = {entry.partition(":")[0] for c in declaring for entry in c.rule_ids}
    scanners = [c.id for c in bundle.of_type(SCANNER_TYPE) if c.code in tools]
    guardrails = [c.id for c in declaring if c.type in GUARDRAIL_TYPES]
    return scanners, guardrails


def load_context(inventory: Path) -> dict[str, Any]:
    """Applicability context from the AI inventory file; empty when there is none.

    An unknown `risk_tier` is an error: it would otherwise exclude every tier-gated control.
    """
    if not inventory.is_file():
        return {}
    doc = yaml.safe_load(inventory.read_text(encoding="utf-8")) or {}
    if "risk_tier" in doc and doc["risk_tier"] not in RISK_TIERS:
        raise ValueError(f"{inventory}: risk_tier {doc['risk_tier']!r} is not one of {RISK_TIERS}")
    return {field: doc[field] for field in CONTEXT_FIELDS if field in doc}


def _suppression_entry(finding: Finding, s: Suppression, keys: list[str]) -> dict[str, Any]:
    return {
        "finding": finding,
        "suppression": s.id,
        "kind": s.kind,
        "controls": keys,
        "owner": s.owner,
        "expires": s.expires.isoformat(),
        "reason": s.reason,
    }


def map_findings(
    bundle: Bundle, findings: list[Finding], context: dict[str, Any] | None = None, today: date | None = None
) -> dict[str, Any]:
    """Build the mapping document (spec §5.4) from a bundle, findings, an applicability context, and a date.

    Active suppressions (Spec C) change how a matching finding is counted, never whether it is shown:
    a false positive leaves its control or the gap list; an accepted risk stays on its control, marked.
    A suppression approved after `today` is an error: it would otherwise appear in no list at all.
    """
    today = today or datetime.now(UTC).date()
    suppressions = bundle.suppressions()
    if pending := [s.id for s in suppressions if s.approved > today]:
        raise ValueError(f"suppressions approved after {today}: {pending}")
    active = [s for s in suppressions if s.active(today)]
    used: set[str] = set()
    controls: dict[str, dict[str, Any]] = {}
    for c in bundle.controls():
        evidenced_by, satisfied_by = _evidence(bundle, c.key)
        controls[c.key] = {
            "status": "",
            "findings": [],
            "evidenced_by": evidenced_by,
            "satisfied_by": satisfied_by,
        }
        if not applies(c, context or {}):
            controls[c.key] |= {"status": "not-applicable", "reason": "control-not-applicable"}
    unmapped: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for finding in findings:
        keys, reason = _controls_for(bundle, finding)
        match = next((s for s in active if s.matches(finding)), None)
        if match:
            used.add(match.id)
            suppressed.append(_suppression_entry(finding, match, keys))
            if match.kind == "false-positive":
                continue
            finding = finding | {"accepted": match.id}
        if reason:
            unmapped.append({"finding": finding, "reason": reason})
        for key in keys:
            controls[key]["findings"].append(finding)
    for entry in controls.values():
        if entry["status"] == "not-applicable":
            continue
        if entry["findings"]:
            entry["status"] = "not-satisfied"
        elif entry["evidenced_by"] or entry["satisfied_by"]:
            entry["status"] = "no-violations-detected"
        else:
            entry["status"] = "not-assessed"
    mapping: dict[str, Any] = {"controls": controls, "unmapped": unmapped}
    if suppressions:
        mapping |= {
            "suppressed": suppressed,
            "expired_suppressions": [s.id for s in suppressions if today > s.expires],
            "unused_suppressions": [s.id for s in active if s.id not in used],
            "expiring_suppressions": [
                {"id": s.id, "expires": s.expires.isoformat()}
                for s in active
                if (s.expires - today).days <= EXPIRY_WARNING_DAYS
            ],
        }
    return mapping


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--target", type=Path, default=Path("app"), help="scan target; its ai-inventory.yaml sets the risk tier")
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="date for suppression expiry")
    args = parser.parse_args(argv)
    findings = json.loads((args.out / "findings.json").read_text(encoding="utf-8"))
    mapping = map_findings(load_bundle(args.knowledge), findings, load_context(args.target / "ai-inventory.yaml"), args.today)
    (args.out / "mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
