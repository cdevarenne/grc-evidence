"""`grc propose`: coverage gaps as a mapping patch and an issue body, from `grc triage`'s proposals (Spec G G4).

A gap triage mapped to an in-bundle control with high confidence becomes a draft `Scanner Check` concept in
`out/agent/mapping.patch`; the gaps no control covers are listed in `out/agent/gaps.md`. Nothing outside
`out/agent/` is written: a person applies the patch, writes each draft section, deletes the marker lines and
signs the concept; until then `grc check` fails on it.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import yaml

from grc_evidence.config import load_config
from grc_evidence.contract import read_mapping
from grc_evidence.digest import scan_digest
from grc_evidence.errors import GrcError
from grc_evidence.narrate import mapping_sha256
from grc_evidence.okf_lib import DEFAULT_FRAMEWORK, Bundle, Concept, load_bundle
from grc_evidence.suppress import MARKER_LINE, slug

Json = dict[str, Any]
DOC_KEYS = ("mapping_sha256", "model", "variant", "abstain_on", "proposals")
_LITERAL_RULE = re.compile(r"[^:\s]+:[^*?\[\]]+")  # the loader's `<tool>:<literal prefix>` without `*`: one exact rule


class ProposeError(GrcError):
    """Proposals `grc propose` refuses to draft from."""


def read_proposals(out: Path) -> Json:
    """`out/proposals.json`, refused unless it names its inputs and was made from the current `out/mapping.json`."""
    path = out / "proposals.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not all(k in doc for k in DOC_KEYS):
        raise ProposeError(f"{path} does not name the mapping it was made from (grc-evidence 2.2.0 or earlier); rerun grc triage")
    if doc["mapping_sha256"] != mapping_sha256(out / "mapping.json"):
        raise ProposeError(f"{path} was made from another mapping.json; rerun grc triage")
    return doc


def quote(text: Any) -> str:
    """Scanner or model text on one line: never a heading, a markdown link, a code span or a table cell break."""
    return " ".join(str(text).split()).replace("](", "] (").replace("|", "\\|").replace("`", "'")


def _configuration(doc: Json) -> str:
    return (f"`grc triage` ({quote(doc['model'])}, {quote(doc['variant'])}, abstain on {quote(doc['abstain_on'])}) "
            f"on the mapping {quote(doc['mapping_sha256'])[:12]}")


def _accuracy_link() -> str:
    return f"https://github.com/cdevarenne/grc-evidence/blob/v{version('grc-evidence')}/docs/llm.md"


def _concept(control: Concept, gap: Json, proposal: Json, doc: Json, now: str) -> str:
    rule = f"{gap['tool']}:{gap['rule_id']}"
    fm = {
        "type": "Scanner Check",
        "title": f"{gap['tool']} {gap['rule_id']}",
        "tags": [control.code if control.framework == DEFAULT_FRAMEWORK else control.key],  # its key as a tag: cc7.1
        "rule_ids": [rule],
        "generated": {"by": f"{doc['model']} via grc triage", "at": now},
    }
    targets = ", ".join(f"`{quote(t)}`" for t in gap["targets"])
    n = gap["count"]
    lines = [
        "# Rule", "", MARKER_LINE, "",
        (f'The scanner reported (quoted as reported): "{quote(gap["message"])}" in {targets} '
         f"({n} finding{'s' if n != 1 else ''})."),
        f'`grc triage` proposed this control with high confidence: "{quote(proposal["rationale"])}"',
        "", "# Satisfies", "", f"- [{control.title}]({posixpath.relpath(control.path, 'policies')})",
        "", "# Enforced at", "", f"- Detected by {quote(gap['tool'])} (listed in `rule_ids`); no rule of this bundle enforces it",
        "", "# Remediation", "", MARKER_LINE,
    ]
    return f"---\n{yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=1000)}---\n" + "\n".join(lines) + "\n"


def _new_file(path: str, text: str) -> str:
    """A `git`-style diff that creates `path` with `text`."""
    lines = text.splitlines()
    head = [f"diff --git a/{path} b/{path}", "new file mode 100644", "--- /dev/null", f"+++ b/{path}", f"@@ -0,0 +1,{len(lines)} @@"]
    return "".join(f"{line}\n" for line in [*head, *(f"+{line}" for line in lines)])


def _why_not(proposal: Json) -> str:
    if proposal["proposal"] == "invalid":
        return "invalid: " + "; ".join(map(str, proposal.get("errors", [])))
    leaned = proposal.get("cutoff_from") or (proposal["proposal"] if proposal["proposal"] != "none" else None)
    return f"none (leaned {leaned}, {proposal['confidence']})" if leaned else "none"


def drafts(bundle: Bundle, mapping: Json, doc: Json, knowledge: str, now: str) -> tuple[str, str, list[str]]:
    """(patch text, issue body, skipped `rule: reason` lines); a text is empty when there is nothing to put in it.

    Every gap is drafted or is a row of the issue body; only a proposal for a rule that is not a gap is skipped.
    """
    gaps = {f"{g['tool']}:{g['rule_id']}": g for g in scan_digest(mapping, targets=True)["gaps"]}
    files: dict[str, tuple[str, str, str]] = {}  # path in the repo: rule, control key, text
    rows, skipped = [], []
    for p in doc["proposals"]:
        rule, key = p["rule"], p["proposal"]
        if (gap := gaps.get(rule)) is None:
            skipped.append(f"{quote(rule)}: not a coverage gap in out/mapping.json")
            continue
        if key in ("none", "invalid") or p.get("confidence") != "high":
            rows.append(f"| `{quote(rule)}` | {gap['count']} | {quote(_why_not(p))} |")
            continue
        concept_id = f"policies/{slug(gap['tool'], gap['rule_id'])}"
        path = f"{knowledge}/{concept_id}.md"
        if (control := bundle.control(key)) is None:
            why = "control not in the bundle"
        elif not _LITERAL_RULE.fullmatch(rule):
            why = "not a literal rule id (no whitespace in the tool, no * ? [ ])"
        elif concept_id in bundle.concepts:
            why = f"{path} exists"
        elif path in files:
            why = f"{path} is drafted for {files[path][0]}"
        else:
            files[path] = (quote(rule), key, _concept(control, gap, p, doc, now))
            continue
        rows.append(f"| `{quote(rule)}` | {gap['count']} | {quote(f'{key} (high): {why}')} |")
    patch = ""
    if files:
        notes = [f"# grc propose: draft Scanner Check concepts from {_configuration(doc)}.",
                 f"# How often triage is right: {_accuracy_link()}",
                 "# Apply with `git apply`; write each draft section, delete the marker lines, and sign each concept.",
                 *(f"# - {rule} -> {key}: {path}" for path, (rule, key, _) in files.items())]
        patch = "\n".join(notes) + "\n\n" + "".join(_new_file(path, text) for path, (_, _, text) in files.items())
    issue = ""
    if rows:
        issue = "\n".join(["# Coverage gaps no control covers", "", f"From {_configuration(doc)}.",
                           f"How often triage is right: {_accuracy_link()}", "",
                           "| Rule | Findings | Why no draft |", "|---|---|---|", *rows]) + "\n"
    return patch, issue, skipped


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="grc propose", description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="scan layout (default: grc.yaml if present)")
    parser.add_argument("--knowledge", default=None, help="knowledge bundle (overrides the config)")
    parser.add_argument("--out", type=Path, default=Path("out"), help="where mapping.json and proposals.json are")
    args = parser.parse_args(argv)
    knowledge = Path(load_config(Path.cwd(), args.config, knowledge=args.knowledge).knowledge)
    mapping = read_mapping(args.out / "mapping.json")
    doc = read_proposals(args.out)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    patch, issue, skipped = drafts(load_bundle(knowledge), mapping, doc, knowledge.as_posix(), now)
    agent = args.out / "agent"
    for name, text in (("mapping.patch", patch), ("gaps.md", issue)):
        if text:
            agent.mkdir(parents=True, exist_ok=True)
            (agent / name).write_text(text, encoding="utf-8")
        else:
            (agent / name).unlink(missing_ok=True)
    drafted, listed = patch.count("\ndiff --git "), issue.count("\n| `")
    print(f"propose: {drafted} draft concept(s) in {agent / 'mapping.patch'}, {listed} gap(s) in {agent / 'gaps.md'}; "
          "nothing applied to the bundle")
    for line in skipped:
        print(f"  skipped {line}")
    if drafted:
        print(f"Next: git apply {agent / 'mapping.patch'}; write each draft section, delete the marker lines, sign; grc check.")
    if listed:
        print(f"For the gaps: gh issue create --title 'Coverage gaps' -F {agent / 'gaps.md'}")


if __name__ == "__main__":
    main()
