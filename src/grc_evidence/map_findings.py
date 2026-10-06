"""Join normalized findings to in-bundle controls; never invent a mapping."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from grc_evidence.config import ConfigError, load_config
from grc_evidence.contract import read_findings
from grc_evidence.data import SCHEMA_VERSION
from grc_evidence.okf_lib import (
    EXPIRY_WARNING_DAYS,
    GUARDRAIL_TYPES,
    SCANNER_TYPE,
    Bundle,
    Suppression,
    applies,
    load_bundle,
)
from grc_evidence.run_scan import tools_not_run

Finding = dict[str, Any]
CONTEXT_FIELDS = ("risk_tier",)  # inventory fields that `applies_when` may name
RISK_TIERS = ("minimal", "limited", "high")  # EU AI Act risk classes the inventory may declare
SDK_GAP = "rules-do-not-cover-sdk"  # not-assessed: the only rules cannot read the AI SDKs the inventory declares
NOT_RUN = "rules-not-run"  # not-assessed: every rule declared for the control belongs to a scanner that did not run


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
    `ai_sdks` is set only when every inventoried AI system names its `sdk`: an unknown SDK rules nothing out.
    """
    if not inventory.is_file():
        return {}
    doc = yaml.safe_load(inventory.read_text(encoding="utf-8")) or {}
    if "risk_tier" in doc and doc["risk_tier"] not in RISK_TIERS:
        raise ConfigError(f"{inventory}: risk_tier {doc['risk_tier']!r} is not one of {RISK_TIERS}")
    context = {field: doc[field] for field in CONTEXT_FIELDS if field in doc}
    systems = doc.get("systems") or []
    if not isinstance(systems, list) or not all(isinstance(s, dict) for s in systems):
        raise ConfigError(f"{inventory}: systems must be a list of mappings")
    sdks = [s.get("sdk") for s in systems]
    if sdks and all(isinstance(sdk, str) and sdk for sdk in sdks):
        context["ai_sdks"] = sorted(set(sdks))
    return context


def _sdk_gap(bundle: Bundle, key: str, context: dict[str, Any]) -> bool:
    """The control's only evidence is SDK-scoped rules, and none of them reads an SDK the inventory declares."""
    declaring = bundle.declaring(key)
    if not context.get("ai_sdks") or not declaring or not all(c.frontmatter.get("sdks") for c in declaring):
        return False
    return not set(context["ai_sdks"]) & {sdk for c in declaring for sdk in c.frontmatter["sdks"]}


def _rules_not_run(bundle: Bundle, key: str, context: dict[str, Any]) -> bool:
    """Every rule declared for the control belongs to a tool the layout turned off (`tools_not_run`)."""
    rules = [r for c in bundle.declaring(key) for r in c.rule_ids]
    return bool(rules) and all(r.partition(":")[0] in context.get("tools_not_run", ()) for r in rules)


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
    A suppression approved after `today` (a reviewer's date east of UTC, or a typo) is pending: not applied, and listed.
    """
    today = today or datetime.now(UTC).date()
    suppressions = bundle.suppressions()
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
    for key, entry in controls.items():
        if entry["status"] == "not-applicable":
            continue
        if entry["findings"]:
            entry["status"] = "not-satisfied"
        elif _rules_not_run(bundle, key, context or {}):
            entry |= {"status": "not-assessed", "reason": NOT_RUN}
        elif _sdk_gap(bundle, key, context or {}):
            entry |= {"status": "not-assessed", "reason": SDK_GAP}
        elif entry["evidenced_by"] or entry["satisfied_by"]:
            entry["status"] = "no-violations-detected"
        else:
            entry["status"] = "not-assessed"
    mapping: dict[str, Any] = {"controls": controls, "unmapped": unmapped}
    if suppressions:
        mapping |= {
            "suppressed": suppressed,
            "expired_suppressions": [s.id for s in suppressions if today > s.expires],
            "pending_suppressions": [{"id": s.id, "approved": s.approved.isoformat()} for s in suppressions if s.approved > today],
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
    parser.add_argument("--config", type=Path, default=None, help="scan layout (default: grc.yaml if present)")
    parser.add_argument("--knowledge", default=None, help="knowledge bundle (overrides the config)")
    parser.add_argument("--target", default=None, help="scan target, whose inventory sets the risk tier (overrides the config)")
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="date for suppression expiry")
    args = parser.parse_args(argv)
    config = load_config(Path.cwd(), args.config, target=args.target, knowledge=args.knowledge)
    findings = read_findings(args.out / "findings.json")
    inventory = Path(config.target) / config.inventory
    context = load_context(inventory) | ({"tools_not_run": not_run} if (not_run := tools_not_run(config)) else {})
    mapping = map_findings(load_bundle(Path(config.knowledge)), findings, context, args.today)
    doc = {"schema_version": SCHEMA_VERSION, **mapping}
    (args.out / "mapping.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
