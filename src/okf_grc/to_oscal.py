"""Render a control mapping as OSCAL 1.2.3 component-definition, assessment-plan, and assessment-results (documented subset)."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from okf_grc import data
from okf_grc.config import Config, load_config
from okf_grc.map_findings import NOT_RUN, SDK_GAP
from okf_grc.okf_lib import (
    COMPONENT_TYPE,
    FRAMEWORK_TYPES,
    MAX_SUPPRESSION_DAYS,
    Bundle,
    Concept,
    load_bundle,
)
from okf_grc.run_scan import SEVERITIES, conftest_inputs, load_pins, scanner_runs

OSCAL_VERSION = "1.2.3"
DOC_VERSION = "0.1.0"
Json = dict[str, Any]
NAMESPACE = uuid.UUID("6f1c3a52-2d0e-5b8e-9c61-0b8f4a7d2e10")
TSC_RESOURCE = "tsc-2017"
# One back-matter resource per framework: the `source` of its control-implementations.
# ISO/IEC 42001 has no official OSCAL catalog, so its resource is a clean-room placeholder.
SOURCES: dict[str, Json] = {
    "soc2": {"id": TSC_RESOURCE, "title": "AICPA Trust Services Criteria (SOC 2)", "label": "SOC 2 criteria"},
    "iso42001": {
        "id": "iso42001-annex-a",
        "title": "ISO/IEC 42001:2023 Annex A (placeholder: no official OSCAL catalog; control ids only)",
        "label": "ISO/IEC 42001 Annex A controls",
    },
    "eu-ai-act": {
        "id": "eu-ai-act-2024-1689",
        "title": "Regulation (EU) 2024/1689 (EU AI Act)",
        "label": "EU AI Act articles",
        "href": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
    },
}
AP_HREF = "assessment-plan.json"  # relative: the OSCAL files are written side by side in out/oscal/
NO_SSP_HREF = "#system-security-plan-not-modeled"
# Namespace for this repo's own props (OSCAL reserves un-namespaced names for NIST-defined ones).
PROP_NS = "https://github.com/cdevarenne/okf-grc-skill/ns/oscal"
SUPPRESSION_POLICY = (
    "A finding may be suppressed only by a suppression concept in the knowledge bundle that matches it exactly "
    "(tool, rule id, target, and optionally a message fragment; no wildcards), names a human owner and a reason, "
    "carries a human `verified` entry, and expires at most {days} days after approval. A false positive leaves "
    "the control's status and is named in the results' remarks; an accepted risk keeps the control not-satisfied "
    "and is recorded as a deviation-approved risk. An expired suppression no longer applies."
)
GROUNDING_RULE = (
    "A finding maps to a control only through a `rule_ids` declaration in the knowledge bundle. A finding no "
    "declaration covers is a coverage gap, recorded as an open risk, never as a control finding. A clean "
    "automated scan evidences a control but never attests it."
)


def _uuid(*parts: str) -> str:
    """Deterministic UUIDv5 so re-runs on the same input produce the same ids."""
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


def _metadata(title: str, now: str) -> Json:
    return {"title": title, "last-modified": now, "version": DOC_VERSION, "oscal-version": OSCAL_VERSION}


def _finding_key(f: Json) -> str:
    return f"{f['tool']}:{f['rule_id']}:{f['target']}:{f['message']}"


def _resource(framework: str) -> Json:
    source = SOURCES[framework]
    resource: Json = {"uuid": _uuid("resource", source["id"]), "title": source["title"]}
    if "href" in source:
        resource["rlinks"] = [{"href": source["href"]}]
    return resource


def _control_implementation(comp: Concept, framework: str, controls: list[Concept]) -> Json:
    """The controls of one framework that apply to a component; control-ids are codes within that source."""
    return {
        "uuid": _uuid("control-implementation", comp.id, framework),
        "source": f"#{_resource(framework)['uuid']}",
        "description": f"{SOURCES[framework]['label']} that apply to {comp.title}.",
        "implemented-requirements": [
            {"uuid": _uuid("req", comp.id, c.key), "control-id": c.code, "description": c.title}
            for c in controls
        ],
    }


def component_definition(bundle: Bundle, now: str) -> Json:
    """Stack components × the in-bundle controls each one links to that some concept declares rules for.

    Each component gets one control-implementation per framework, each pointing at that framework's source.
    """
    grounded = [c for c in bundle.controls() if bundle.declaring(c.key)]
    components = []
    used: set[str] = set()
    for comp in bundle.of_type(COMPONENT_TYPE):
        controls = [c for cid in comp.links if (c := bundle.concepts.get(cid)) and c in grounded]
        entry: Json = {
            "uuid": _uuid("component", comp.id),
            "type": "software",
            "title": comp.title,
            "description": comp.description or comp.title,
        }
        frameworks = [fw for fw in FRAMEWORK_TYPES if any(c.framework == fw for c in controls)]
        if frameworks:
            entry["control-implementations"] = [
                _control_implementation(comp, fw, [c for c in controls if c.framework == fw]) for fw in frameworks
            ]
        used.update(frameworks)
        components.append(entry)
    resources = [_resource(fw) for fw in FRAMEWORK_TYPES if fw in used] or [_resource("soc2")]
    return {
        "component-definition": {
            "uuid": _uuid("component-definition"),
            "metadata": _metadata("okf-grc-skill sample app components", now),
            "components": components,
            "back-matter": {"resources": resources},
        }
    }


def _component(comp: Concept) -> Json:
    """A stack component with the same UUID as in the component-definition."""
    return {
        "uuid": _uuid("component", comp.id),
        "type": "software",
        "title": comp.title,
        "description": comp.description or comp.title,
        "status": {"state": "operational"},
    }


def _evidenced_by(bundle: Bundle, key: str) -> set[str]:
    """Tools whose rules some concept declares for this control."""
    return {entry.partition(":")[0] for c in bundle.declaring(key) for entry in c.rule_ids}


def assessment_plan(
    bundle: Bundle, mapping: Json, now: str, pins: dict[str, str], config: Config | None = None, repo: Path = Path()
) -> Json:
    """What the automated scan intends to assess: every applicable control, the scanner runs, the components.

    In scope is every control not excluded by the declared AI risk tier, including controls no scanner
    evidences; a planned control the results mark not-assessed is a coverage gap at the control level.
    """
    in_scope = sorted(key for key, c in mapping["controls"].items() if c["status"] != "not-applicable")
    excluded = sorted(key for key, c in mapping["controls"].items() if c["status"] == "not-applicable")
    config = config or Config()
    target = config.target
    runs = scanner_runs(config, conftest_inputs(repo, config))
    activities = []
    for run in runs:
        command = " ".join(run.argv)
        activity: Json = {
            "uuid": _uuid("activity", command),
            "title": run.title,
            "description": f"Run {run.tool} {pins[run.pin]} over `{target}` and normalize its JSON output to findings.",
            "props": [
                {"name": "method", "value": "TEST"},
                {"name": "tool-version", "ns": PROP_NS, "value": pins[run.pin]},
            ],
            "steps": [
                {
                    "uuid": _uuid("step", command),
                    "title": "Run the scanner",
                    "description": f"`{command}` (working directory: {'the scan target' if run.in_target else 'the repository root'})",
                }
            ],
        }
        if selections := _control_selections(bundle, [k for k in in_scope if run.tool in _evidenced_by(bundle, k)]):
            activity["related-controls"] = {"control-selections": selections}
        activities.append(activity)
    components = [_component(comp) for comp in bundle.of_type(COMPONENT_TYPE)]
    scope: Json = (
        {"include-subjects": [{"subject-uuid": c["uuid"], "type": "component"} for c in components]}
        if components
        else {"include-all": {}}
    )
    subjects = [
        {
            "type": "component",
            "description": "The stack components described in the knowledge bundle.",
            **scope,
        }
    ]
    tools = {run.tool: pins[run.pin] for run in runs}
    tool_components = [
        {
            "uuid": _uuid("tool", tool),
            "type": "software",
            "title": f"{tool} {version}",
            "description": f"{tool}, pinned to {version} in tools.lock.",
            "props": [{"name": "tool-version", "ns": PROP_NS, "value": version}],
            "status": {"state": "operational"},
        }
        for tool, version in tools.items()
    ]
    reviewed: Json = {
        "description": "Every control applicable at the declared AI risk tier, including controls no scanner evidences.",
        "control-selections": _control_selections(bundle, in_scope),
    }
    if excluded:
        reviewed["remarks"] = f"Not applicable at the declared AI risk tier: {', '.join(excluded)}"
    plan: Json = {
        "uuid": _uuid("assessment-plan", now),
        "metadata": _metadata("okf-grc-skill automated assessment plan", now),
        "import-ssp": {"href": NO_SSP_HREF, "remarks": "System security plan not modeled; see docs/oscal-subset.md."},
        "local-definitions": {"activities": activities},
        "terms-and-conditions": {
            "parts": [
                {"name": "rules-of-engagement", "title": "Suppression policy",
                 "prose": SUPPRESSION_POLICY.format(days=MAX_SUPPRESSION_DAYS)},
                {"name": "methodology", "title": "Grounding rule", "prose": GROUNDING_RULE},
            ]
        },
        "reviewed-controls": reviewed,
        "assessment-subjects": subjects,
        "assessment-assets": {
            "components": tool_components,
            "assessment-platforms": [
                {
                    "uuid": _uuid("platform", "make-scan"),
                    "title": "`make scan` pipeline, scanners pinned in tools.lock",
                    "uses-components": [{"component-uuid": c["uuid"]} for c in tool_components],
                }
            ],
        },
        "tasks": [
            {
                "uuid": _uuid("task", "automated-scan"),
                "type": "action",
                "title": "Automated compliance scan",
                "description": "Run every scanner activity, then map findings to controls through the knowledge bundle.",
                "associated-activities": [{"activity-uuid": a["uuid"], "subjects": subjects} for a in activities],
                "subjects": subjects,
            }
        ],
    }
    if components:
        plan["local-definitions"]["components"] = components
    return {"assessment-plan": plan}


def _severity(level: str) -> Json:
    return {"name": "severity", "ns": PROP_NS, "value": level}


def _observation(f: Json, now: str) -> Json:
    return {
        "uuid": _uuid("observation", _finding_key(f)),
        "title": f"{f['tool']} {f['rule_id']}",
        "description": f"{f['message']} ({f['target']}, severity {f['severity']})",
        "props": [_severity(f["severity"])],
        "methods": ["TEST"],
        "collected": now,
    }


def _remarks(mapping: Json) -> str:
    """Controls without an OSCAL finding, stated so their absence is not read as a pass."""
    groups = [
        ("no-violations-detected", None, "No violations detected by automated checks (not a control attestation)"),
        ("not-assessed", None, "Not assessed (no in-bundle scanner or policy)"),
        ("not-assessed", SDK_GAP, "Not assessed (its only rules do not read the AI SDKs the inventory declares)"),
        ("not-assessed", NOT_RUN, "Not assessed (the scanner its rules belong to did not run)"),
        ("not-applicable", None, "Not applicable at the declared AI risk tier"),
    ]
    parts = []
    for status, reason, label in groups:
        keys = sorted(
            key for key, c in mapping["controls"].items()
            if c["status"] == status and (status != "not-assessed" or c.get("reason") == reason)
        )
        if keys:
            parts.append(f"{label}: {', '.join(keys)}")
    return ". ".join(parts)


def _control_selections(bundle: Bundle, assessed: list[str]) -> list[Json]:
    """One control selection per framework; control-ids are codes within that framework's source."""
    selections = []
    for fw in FRAMEWORK_TYPES:
        codes = [key.partition(":")[2] for key in assessed if key.partition(":")[0] == fw]
        if codes:
            selections.append(
                {"description": SOURCES[fw]["title"], "include-controls": [{"control-id": c} for c in codes]}
            )
    return selections


def assessment_results(bundle: Bundle, mapping: Json, now: str, run_id: str | None = None) -> Json:
    """Findings only for controls with violations; unmapped findings become open risks, never findings.

    A clean automated scan never produces a `satisfied` finding: automation evidences a
    control but does not attest it. A `not-applicable` control is neither reviewed nor a finding.
    """
    suppressed = mapping.get("suppressed", [])
    all_findings = [f for c in mapping["controls"].values() for f in c["findings"]]
    all_findings += [u["finding"] for u in mapping["unmapped"]]
    all_findings += [s["finding"] for s in suppressed if s["kind"] == "false-positive"]
    observations = {_finding_key(f): _observation(f, now) for f in all_findings}
    assessed = sorted(
        key for key, c in mapping["controls"].items() if c["status"] not in ("not-assessed", "not-applicable")
    )
    findings = []
    for key in assessed:
        entry = mapping["controls"][key]
        if entry["status"] != "not-satisfied":
            continue
        control = bundle.control(key)
        accepted = sum(1 for f in entry["findings"] if "accepted" in f)
        description = f"{len(entry['findings']) - accepted} open finding(s)"
        findings.append(
            {
                "uuid": _uuid("finding", key),
                "title": control.title if control else key,
                "description": f"{description}, {accepted} accepted risk(s)." if accepted else f"{description}.",
                "props": [_severity(min((f["severity"] for f in entry["findings"]), key=SEVERITIES.index))],
                "target": {
                    "type": "objective-id",
                    "target-id": key.partition(":")[2],
                    "status": {"state": "not-satisfied"},
                },
                "related-observations": [
                    {"observation-uuid": observations[_finding_key(f)]["uuid"]} for f in entry["findings"]
                ],
            }
        )
    risks = [
        {
            "uuid": _uuid("risk", _finding_key(u["finding"])),
            "title": f"Coverage gap: {u['finding']['tool']} {u['finding']['rule_id']}",
            "description": f"No in-bundle control covers this finding ({u['reason']}).",
            "statement": u["finding"]["message"],
            "status": "open",
            "related-observations": [{"observation-uuid": observations[_finding_key(u["finding"])]["uuid"]}],
        }
        for u in mapping["unmapped"]
    ]
    risks += [
        {
            "uuid": _uuid("risk", "accepted", _finding_key(a["finding"])),
            "title": f"Accepted risk: {a['finding']['tool']} {a['finding']['rule_id']}",
            "description": f"{a['reason']} Accepted by {a['owner']} until {a['expires']} ({a['suppression']}).",
            "statement": a["finding"]["message"],
            "status": "deviation-approved",
            "related-observations": [{"observation-uuid": observations[_finding_key(a["finding"])]["uuid"]}],
        }
        for a in suppressed
        if a["kind"] == "accepted-risk"
    ]
    result: Json = {
        "uuid": _uuid("result"),
        "title": "Automated compliance scan",
        "description": "Scanner findings mapped to in-bundle controls through the OKF knowledge bundle.",
        "start": now,
        "reviewed-controls": {"control-selections": _control_selections(bundle, assessed)},
    }
    if run_id:  # the run manifest (run.json) that hashes these outputs
        result["props"] = [{"name": "run-id", "ns": PROP_NS, "value": run_id}]
    if observations:
        result["observations"] = list(observations.values())
    if risks:
        result["risks"] = risks
    if findings:
        result["findings"] = findings
    remarks = _remarks(mapping)
    if false_positives := sorted({s["suppression"] for s in suppressed if s["kind"] == "false-positive"}):
        fp = "Suppressed as false positives (reviewed; see the bundle): " + ", ".join(false_positives)
        remarks = f"{remarks}. {fp}" if remarks else fp
    if remarks:
        result["remarks"] = remarks
    return {
        "assessment-results": {
            "uuid": _uuid("assessment-results", now),
            "metadata": _metadata("okf-grc-skill automated assessment", now),
            "import-ap": {"href": AP_HREF},
            "results": [result],
        }
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="scan layout (default: grc.yaml if present)")
    parser.add_argument("--knowledge", default=None, help="knowledge bundle (overrides the config)")
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--now", default=datetime.now(UTC).isoformat(timespec="seconds"))
    parser.add_argument("--lock", type=Path, default=None, help="pinned scanner versions (default: the packaged tools.lock)")
    parser.add_argument("--target", default=None, help="scan target, relative to the repo root (overrides the config)")
    parser.add_argument("--run-id", default=None, help="id of the run manifest these results belong to")
    args = parser.parse_args(argv)
    config = load_config(Path.cwd(), args.config, target=args.target, knowledge=args.knowledge)
    bundle = load_bundle(Path(config.knowledge))
    mapping = json.loads((args.out / "mapping.json").read_text(encoding="utf-8"))
    oscal_dir = args.out / "oscal"
    oscal_dir.mkdir(parents=True, exist_ok=True)
    for name, doc in (
        ("component-definition.json", component_definition(bundle, args.now)),
        ("assessment-plan.json", assessment_plan(bundle, mapping, args.now, load_pins(args.lock or data.path("tools.lock")), config)),
        ("assessment-results.json", assessment_results(bundle, mapping, args.now, args.run_id)),
    ):
        (oscal_dir / name).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
