"""Join normalized findings to in-bundle controls; never invent a mapping."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from okf_lib import GUARDRAIL_TYPES, SCANNER_TYPE, Bundle, applies, load_bundle

Finding = dict[str, Any]
CONTEXT_FIELDS = ("risk_tier",)  # inventory fields that `applies_when` may name


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
    """Applicability context from the AI inventory file; empty when there is none."""
    if not inventory.is_file():
        return {}
    doc = yaml.safe_load(inventory.read_text(encoding="utf-8")) or {}
    return {field: doc[field] for field in CONTEXT_FIELDS if field in doc}


def map_findings(bundle: Bundle, findings: list[Finding], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the mapping document (spec §5.4) from a bundle, findings, and an applicability context."""
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
    for finding in findings:
        keys, reason = _controls_for(bundle, finding)
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
    return {"controls": controls, "unmapped": unmapped}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--inventory", type=Path, default=Path("app/ai-inventory.yaml"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    findings = json.loads((args.out / "findings.json").read_text(encoding="utf-8"))
    mapping = map_findings(load_bundle(args.knowledge), findings, load_context(args.inventory))
    (args.out / "mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
