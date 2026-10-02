"""Render the control mapping as an auditor-facing markdown report."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from okf_grc.config import load_config
from okf_grc.map_findings import NOT_RUN, SDK_GAP
from okf_grc.narrate import read_narratives
from okf_grc.okf_lib import FRAMEWORK_TITLES, Bundle, load_bundle

Json = dict[str, Any]

SEVERITIES = ("critical", "high", "medium", "low")  # known severities, ordered high-to-low
UNCLASSIFIED = "unclassified"  # a finding the scanner did not severity-rank
SKIPPED = ("not-assessed", "not-applicable")  # statuses listed at the end, not in the framework sections


def _bucket(severity: str) -> str:
    """Map a scanner severity to a known bucket, or 'unclassified'."""
    s = (severity or "").strip().lower()
    return s if s in SEVERITIES else UNCLASSIFIED


def _counts(findings: list[Json]) -> dict[str, int]:
    """Count findings per severity bucket."""
    counts = dict.fromkeys((*SEVERITIES, UNCLASSIFIED), 0)
    for f in findings:
        counts[_bucket(f["severity"])] += 1
    return counts


def _breakdown(counts: dict[str, int]) -> str:
    """One-line severity breakdown, e.g. '3 critical, 16 high'. Empty buckets are omitted."""
    parts = [f"{counts[s]} {s}" for s in (*SEVERITIES, UNCLASSIFIED) if counts[s]]
    return ", ".join(parts) if parts else "no findings"


def _link(bundle: Bundle, concept_id: str) -> str:
    concept = bundle.concepts[concept_id]
    return f"[{concept.title}](../knowledge/{concept.path})"


def _finding_line(f: Json) -> str:
    line = f"- `{f['tool']}` `{f['rule_id']}` ({f['severity']}) — {f['message']} — `{f['target']}`"
    return f"{line} — **accepted risk** (`{f['accepted']}`)" if f.get("accepted") else line


def _remediation(bundle: Bundle, key: str, findings: list[Json]) -> str:
    """Join the `# Remediation` sections of concepts that declare these findings' rules for this control."""
    paragraphs: dict[str, None] = {}
    for f in findings:
        for concept in bundle.by_rule(f["tool"], f["rule_id"]):
            text = bundle.section(concept, "Remediation")
            if key in concept.control_keys and text:
                paragraphs[text] = None
    return " ".join(paragraphs)


def _order(key: str) -> tuple[int, list[int | str]]:
    """Sort key: framework order (SOC 2 first), then the code in natural order (art-9 before art-10)."""
    framework, _, code = key.partition(":")
    return list(FRAMEWORK_TITLES).index(framework), [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", code)]


def _title(bundle: Bundle, key: str) -> str:
    control = bundle.control(key)
    return control.title if control else key


def _control_section(bundle: Bundle, key: str, entry: Json, narrative: Json | None = None) -> list[str]:
    evidence = [_link(bundle, cid) for cid in entry["evidenced_by"] + entry["satisfied_by"]]
    lines = [f"### {_title(bundle, key)}", "", f"**Status:** {entry['status']}", ""]
    if narrative:
        lines += [f"**Summary (LLM):** {narrative['summary']}", "", f"**Auditor note (LLM):** {narrative['auditor_note']}", ""]
    if entry["findings"]:
        lines += [f"**Findings:** {_breakdown(_counts(entry['findings']))}", ""]
    lines += [f"**Evidence:** {', '.join(evidence) if evidence else 'none in bundle'}", ""]
    if entry["findings"]:
        lines += ["**Open findings:**", "", *map(_finding_line, entry["findings"]), ""]
        if remediation := _remediation(bundle, key, entry["findings"]):
            lines += [f"**Remediation:** {remediation}", ""]
    return lines


def _risk_posture(controls: list[tuple[str, Json]], unmapped: list[Json], suppressed: list[Json]) -> list[str]:
    """A one-glance summary: open findings by severity, control status counts, gaps, and suppressions.

    Accepted risks keep their control `not-satisfied` but are counted apart from open findings.
    """
    total = dict.fromkeys((*SEVERITIES, UNCLASSIFIED), 0)
    open_findings = not_satisfied = accepted_only = not_assessed = not_applicable = clean = 0
    for _key, entry in controls:
        status = entry["status"]
        if status == "not-applicable":
            not_applicable += 1
            continue
        if status == "not-assessed":
            not_assessed += 1
        elif status == "not-satisfied":
            # a control whose findings are all accepted risks is counted apart, so every applicable control is counted once
            has_open = any(not f.get("accepted") for f in entry["findings"])
            not_satisfied += has_open
            accepted_only += not has_open
        else:
            clean += 1
        for f in entry["findings"]:
            if f.get("accepted"):
                continue
            total[_bucket(f["severity"])] += 1
            open_findings += 1
    findings_word = "finding" if open_findings == 1 else "findings"
    clean_clause = "control shows" if clean == 1 else "controls show"
    gaps_word = "coverage gap" if len(unmapped) == 1 else "coverage gaps"
    applicable = len(controls) - not_applicable
    controls_word = "control" if applicable == 1 else "controls"
    na_clause = f" {not_applicable} not applicable." if not_applicable else ""
    accepted_clause = (
        f" {accepted_only} {'control has' if accepted_only == 1 else 'controls have'} only accepted risks."
        if accepted_only
        else ""
    )
    accepted = sum(s["kind"] == "accepted-risk" for s in suppressed)
    false_pos = len(suppressed) - accepted
    suppressed_clause = (
        f" {accepted} accepted {'risk' if accepted == 1 else 'risks'} and {false_pos} "
        f"{'false positive' if false_pos == 1 else 'false positives'} suppressed after review."
        if suppressed
        else ""
    )
    return [
        "## Risk posture",
        "",
        f"{open_findings} open {findings_word} across {not_satisfied} of {applicable} {controls_word}: "
        f"{_breakdown(total)}.",
        f"{clean} {clean_clause} no violations.{accepted_clause} {not_assessed} not assessed.{na_clause} "
        f"{len(unmapped)} {gaps_word} to triage.{suppressed_clause}",
        "",
    ]


def _table_text(text: str) -> str:
    """Bundle prose as one table cell: links become their text (bundle-relative paths break here), `|` escaped."""
    plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", " ".join(text.split()))
    return plain.replace("|", "\\|")


def _suppression_sections(mapping: Json) -> list[str]:
    """Suppressed, expiring, expired, pending, and unused suppressions; each section appears only when it has entries."""
    lines: list[str] = []
    if suppressed := mapping.get("suppressed"):
        lines += ["", "## Suppressed", "", "Reviewed and time-limited. Shown here so nothing is hidden.", ""]
        lines += ["| Kind | Finding | Owner | Expires | Reason |", "|---|---|---|---|---|"]
        for s in suppressed:
            f = s["finding"]
            reason = _table_text(s["reason"])
            lines.append(
                f"| {s['kind']} | `{f['tool']}` `{f['rule_id']}` — `{f['target']}` | {s['owner']} | {s['expires']} | {reason} |"
            )
    if expiring := mapping.get("expiring_suppressions"):
        lines += ["", "## Expiring soon", "", "Renew after a fresh review, or remove.", ""]
        lines += [f"- `{e['id']}` expires {e['expires']}" for e in expiring]
    if expired := mapping.get("expired_suppressions"):
        lines += ["", "## Expired suppressions", "", "No longer applied; their findings count again. Renew or remove.", ""]
        lines += [f"- `{sid}`" for sid in expired]
    if pending := mapping.get("pending_suppressions"):
        lines += ["", "## Pending suppressions", "", "Approved after this scan's date, so not applied yet; their findings count.", ""]
        lines += [f"- `{p['id']}` approved {p['approved']}" for p in pending]
    if unused := mapping.get("unused_suppressions"):
        lines += ["", "## Unused suppressions", "", "Match no finding in this scan. Remove them.", ""]
        lines += [f"- `{sid}`" for sid in unused]
    return lines


def _crosswalk(bundle: Bundle, mapping: Json) -> list[str]:
    """Crosswalk table: linked control pairs from Crosswalk concepts, each side with its own status."""
    pairs = bundle.crosswalk_pairs()
    if not pairs:
        return []
    lines = ["## Crosswalk", "", "Links between frameworks. A link is navigation, never a mapping: each status", "comes only from that control's own rule declarations.", ""]
    lines += ["| Control | Status | Linked control | Status | Source |", "|---|---|---|---|---|"]
    for cw_id, left_id, right_id in pairs:
        left, right = bundle.concepts[left_id], bundle.concepts[right_id]
        lines.append(
            f"| {left.key} | {mapping['controls'][left.key]['status']} | {right.key} | "
            f"{mapping['controls'][right.key]['status']} | {_link(bundle, cw_id)} |"
        )
    return [*lines, ""]


def _llm_footer(usage: list[Json]) -> list[str]:
    """One line on the LLM step's own cost, from this run's ledger entries."""
    if not usage:
        return []
    total = {k: sum(e[k] for e in usage) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cost_usd")}
    models = ", ".join(sorted({e["model"] for e in usage}))
    modes = ", ".join(sorted({e["mode"] for e in usage}))
    billed = sum(e["billed"] for e in usage)
    return [
        "",
        "---",
        "",
        f"LLM step: {len(usage)} call(s), {billed} billed, model {models}, mode {modes}. "
        f"Tokens: {total['input_tokens']} in, {total['output_tokens']} out, "
        f"{total['cache_read_input_tokens']} cache read. Cost ${total['cost_usd']:.4f}. "
        "The LLM wrote prose only; every status and count above is deterministic.",
    ]


def render_report(
    bundle: Bundle, mapping: Json, now: str, narratives: Json | None = None, usage: list[Json] | None = None
) -> str:
    """Markdown report: risk posture, summary, one section per framework, crosswalk, gaps, the rest."""
    controls = sorted(mapping["controls"].items(), key=lambda kv: _order(kv[0]))
    lines = [
        "# Compliance Scan Report",
        "",
        f"Generated {now}. Every status below is derived from scanner findings joined to",
        "controls declared in the OKF knowledge bundle; nothing is mapped without a declaration.",
        "`no-violations-detected` means automated checks found nothing for that control;",
        "it is evidence, not a control attestation.",
        "",
        *_risk_posture(controls, mapping["unmapped"], mapping.get("suppressed", [])),
        "## Summary",
        "",
        "| Control | Status | Critical | High | Medium | Low | Uncl. | Total |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key, entry in controls:
        c = _counts(entry["findings"])
        lines.append(
            f"| {key} | {entry['status']} | {c['critical']} | {c['high']} | "
            f"{c['medium']} | {c['low']} | {c['unclassified']} | {len(entry['findings'])} |"
        )
    lines.append("")
    for fw, fw_title in FRAMEWORK_TITLES.items():
        shown = [(k, e) for k, e in controls if k.partition(":")[0] == fw and e["status"] not in SKIPPED]
        if shown:
            lines += [f"## {fw_title}", ""]
            for key, entry in shown:
                lines += _control_section(bundle, key, entry, (narratives or {}).get(key))
    lines += _crosswalk(bundle, mapping)
    lines += ["## Coverage gaps", ""]
    if mapping["unmapped"]:
        lines += ["Findings with no in-bundle control. These are gaps to close, not mappings to invent.", ""]
        lines += [f"{_finding_line(u['finding'])} — reason: `{u['reason']}`" for u in mapping["unmapped"]]
    else:
        lines.append("None.")
    lines += _suppression_sections(mapping)
    lines += ["", "## Not assessed", ""]
    not_assessed = [key for key, entry in controls if entry["status"] == "not-assessed"]
    reasons = dict(controls)
    for key in not_assessed:
        why = {
            SDK_GAP: "its only rules do not read the AI SDKs the inventory declares",
            NOT_RUN: "the scanner its rules belong to did not run (turned off in grc.yaml)",
        }.get(reasons[key].get("reason"), "no in-bundle scanner or policy evidences this control")
        lines.append(f"- {_title(bundle, key)}: {why}.")
    if not not_assessed:
        lines.append("None.")
    not_applicable = [(key, entry) for key, entry in controls if entry["status"] == "not-applicable"]
    if not_applicable:
        lines += ["", "## Not applicable", ""]
        lines += ["Out of scope at the declared AI risk tier. Findings stay listed; they do not change the status.", ""]
        for key, entry in not_applicable:
            lines.append(f"- {_title(bundle, key)}")
            lines += [f"  {_finding_line(f)}" for f in entry["findings"]]
    lines += _llm_footer(usage or [])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="scan layout (default: grc.yaml if present)")
    parser.add_argument("--knowledge", default=None, help="knowledge bundle (overrides the config)")
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--now", default=datetime.now(UTC).isoformat(timespec="seconds"))
    args = parser.parse_args(argv)
    mapping = json.loads((args.out / "mapping.json").read_text(encoding="utf-8"))
    ledger = args.out / "llm-usage.jsonl"
    narratives, stale = read_narratives(args.out)
    if stale:
        print("report: narratives.json was written for another mapping.json; ignored (rerun `grc narrate`)")
    usage = [json.loads(ln) for ln in ledger.read_text(encoding="utf-8").splitlines()] if ledger.is_file() else []
    last_run = [e for e in usage if usage and e["run_id"] == usage[-1]["run_id"]]
    config = load_config(Path.cwd(), args.config, knowledge=args.knowledge)
    report = render_report(load_bundle(Path(config.knowledge)), mapping, args.now, narratives, last_run)
    (args.out / "report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
