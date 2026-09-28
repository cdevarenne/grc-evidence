# Mini Spec C — Suppression Workflow: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A suppression is a reviewed, expiring record in `knowledge/suppressions/` that changes how one exact finding counts, never whether it is shown. A `false-positive` takes its finding out of its control's status and the coverage-gap list; an `accepted-risk` keeps its finding on its control (`not-satisfied`) and is recorded in OSCAL as a `deviation-approved` risk. Expired and unused suppressions are listed in every report.

**Architecture:** `okf_lib` parses and validates `Suppression` concepts (exact match, human owner, reason, window ≤ 90 days) and rejects an accepted risk on a coverage gap at load time. `map_findings` applies active suppressions after mapping and before status, taking the date from `--today`. `to_oscal`, `render_report`, and Spec B's `digest` read three new, optional keys in `mapping.json` (`suppressed`, `expired_suppressions`, `unused_suppressions`); with no suppressions in the bundle, every output is byte-identical to today's.

**Tech Stack:** unchanged (Python 3.14, PyYAML, pytest, jsonschema; OSCAL 1.2.3).

**Spec:** `docs/superpowers/specs/2026-09-28-mini-spec-c-suppression-workflow.md` (reviewed 2026-09-28: accepted risk keeps `not-satisfied`, no new status; 90-day window; suppressions in `knowledge/`).

**Provenance:** every code block in this plan was run in a prototype on 2026-09-28 against the pinned scanners. Tasks 1–5 were replayed in order on a clean checkout of `main` (`1a2cf34`): the unit suite went 370 → 381 → 382 → 384 → 385 passed, all green. With Task 6 applied, `make test-integration` passed 22 tests against the real scan, and the only unit failures were the two expected `not human-verified` checks that the Task 6 gate resolves. The post-expiry path was checked on the real scan with `--today 2026-12-28`: both suppressions listed as expired, the Trivy finding back in the coverage gaps, the CVE back to unmarked.

## Global Constraints

- Everything in the v1 plan's Global Constraints still holds.
- **Commits:** trunk-based on `main`, authored by `cdevarenne`. **Never add a `Co-Authored-By` trailer.** Short subject, `Closes #N` body line. Every commit ships tests; docs-only commits say so.
- **Nothing is hidden.** A suppressed finding always appears somewhere in the report and in OSCAL.
- **No wildcards, no bulk.** One suppression, one exact finding (`tool`, `rule_id`, `target`, optional `message_contains`).
- **Backward compatible outputs.** A bundle with no suppressions produces the same `mapping.json` keys, report, OSCAL, and LLM digests as before this plan; the golden report and the recorded LLM replay tests prove it.
- **The date is an input.** Expiry reads `--today` (default: the current UTC date), so every test is deterministic.

## Task order

Tasks 1 → 5 are sequential (each consumes the previous). **Task 6 is a human gate:** the two sample suppressions need the maintainer's review and a `verified` entry. Task 7 is docs.

## Task 0: Tracking issues (no commit)

- [ ] **Step 1:** Create one issue per task, titled `C1: …` through `C7: …` after the task names below, each body pointing at this plan and task. Note the numbers for the `Closes #` lines.

---

## Task 1: okf_lib: the Suppression concept

**Files:**
- Modify: `.claude/skills/grc-continuous-compliance/scripts/okf_lib.py` (full replacement below)
- Modify: `tests/test_bundle_conformance.py`
- Test: `tests/test_suppressions.py` (new)

**Interfaces:**
- Produces: `SUPPRESSION_TYPE = "Suppression"`, `SUPPRESSION_KINDS`, `MAX_SUPPRESSION_DAYS = 90`; `Suppression` (frozen dataclass: `id, kind, tool, rule_id, target, message_contains, owner, approved, expires, reason`) with `.matches(finding)` and `.active(today)` (inclusive of both dates); `Bundle.suppressions()`.
- `load_bundle` raises `BundleError` naming the file for: an unknown `kind`; a missing `finding.tool/rule_id/target`; a wildcard (`*`, `?`, `[`) in any of them; an `owner` not starting `human:`; an unparseable date; `expires` not strictly after `approved` or more than 90 days after it; an empty `# Reason`; and an `accepted-risk` whose rule maps to no in-bundle control (a gap has no control whose risk is accepted).

- [ ] **Step 1: Write the failing tests.**

`tests/test_suppressions.py`:

```python
"""Suppressions (Spec C): reviewed, expiring, exact; they change how a finding counts, never whether it shows."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from okf_lib import BundleError, load_bundle

FIXTURES = Path(__file__).parent / "fixtures"
FINDINGS = json.loads((FIXTURES / "findings.json").read_text())
IN_FORCE = date(2026, 10, 1)
NOW = "2026-10-01T12:00:00+00:00"


def _suppression(kind: str, tool: str, rule_id: str, target: str, *, approved: str = "2026-09-28",
                 expires: str = "2026-12-27", owner: str = "human:reviewer", extra: str = "",
                 reason: str = "Reviewed: does not apply here.") -> str:
    return (
        f"---\ntype: Suppression\ntitle: t\nkind: {kind}\n"
        f"finding:\n  tool: {tool}\n  rule_id: {rule_id}\n  target: {target}\n{extra}"
        f"owner: {owner}\napproved: \"{approved}\"\nexpires: \"{expires}\"\ntags: [suppression]\n---\n"
        f"# Reason\n\n{reason}\n"
    )


FALSE_POSITIVE = _suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile")
ACCEPTED = _suppression("accepted-risk", "trivy", "CVE-2024-0001", "app/requirements.txt")


def _bundle(tmp_path: Path, **suppressions: str):
    root = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "bundle", root)
    for name, text in suppressions.items():
        (root / "suppressions").mkdir(exist_ok=True)
        (root / "suppressions" / f"{name}.md").write_text(text, encoding="utf-8")
    return load_bundle(root)


# -- validation ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "error"),
    [
        (_suppression("wontfix", "checkov", "CKV_TEST_99", "app/Dockerfile"), "kind"),
        (_suppression("false-positive", "checkov", "CKV_*", "app/Dockerfile"), "wildcards"),
        (_suppression("false-positive", "checkov", "", "app/Dockerfile"), "tool, rule_id, and target"),
        (_suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile", owner="team-a"), "owner"),
        (_suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile", expires="2026-12-28"), "90 days"),
        (_suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile", expires="2026-09-28"), "90 days"),
        (_suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile", approved="soon"), "ISO date"),
        (_suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile", reason=""), "Reason"),
        (_suppression("accepted-risk", "checkov", "CKV_TEST_99", "app/Dockerfile"), "is a gap"),
    ],
)
def test_malformed_suppressions_are_rejected(tmp_path: Path, text: str, error: str) -> None:
    with pytest.raises(BundleError, match=error):
        _bundle(tmp_path, bad=text)


def test_suppressions_load_as_typed_records(tmp_path: Path) -> None:
    (s,) = _bundle(tmp_path, fp=FALSE_POSITIVE).suppressions()
    assert (s.id, s.kind, s.rule_id, s.owner, s.expires) == (
        "suppressions/fp", "false-positive", "CKV_TEST_99", "human:reviewer", date(2026, 12, 27)
    )
    assert s.reason == "Reviewed: does not apply here."
```

In `tests/test_bundle_conformance.py`, add `"Suppression"` to `TYPES`, and append:

```python
def test_suppressions_name_a_known_tool_and_one_owner() -> None:
    """Load-time checks enforce kind, exact match, owner, reason, and the 90-day window; this adds the tool set."""
    for s in BUNDLE.suppressions():
        assert s.tool in TOOLS, f"{s.id}: unknown tool {s.tool!r}"
        assert s.owner.startswith("human:"), s.id
```

Run: `uv run pytest tests/test_suppressions.py -q`
Expected: every validation case fails (no `BundleError` raised), and `suppressions()` is missing.

- [ ] **Step 2: Replace `okf_lib.py`.**

```python
"""Load an OKF v0.2 bundle into an in-memory concept graph."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import yaml

RESERVED = frozenset({"index.md", "log.md"})
SUPPRESSION_TYPE = "Suppression"
SUPPRESSION_KINDS = ("false-positive", "accepted-risk")
MAX_SUPPRESSION_DAYS = 90
CONTROL_TYPE = "SOC 2 Control"
FRAMEWORK_TYPES = {"soc2": CONTROL_TYPE, "iso42001": "ISO/IEC 42001 Control", "eu-ai-act": "EU AI Act Article"}
FRAMEWORK_TITLES = {"soc2": "SOC 2", "iso42001": "ISO/IEC 42001", "eu-ai-act": "EU AI Act"}
DEFAULT_FRAMEWORK = "soc2"
_AI_ONLY = "AI system components only: LLM features, model calls, and the AI inventory"
FRAMEWORK_SCOPES = {"soc2": "any system component", "iso42001": _AI_ONLY, "eu-ai-act": _AI_ONLY}
CROSSWALK_TYPE = "Crosswalk"
SCANNER_TYPE = "Scanner"
GUARDRAIL_TYPES = ("Rego Policy", "Semgrep Rule")
COMPONENT_TYPE = "Stack Component"
_CONTROL_TAG = re.compile(r"^(?:cc\d+\.\d+|iso42001:a\.\d+|eu-ai-act:art-\d+)$")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_H1 = re.compile(r"^# (.+?)\s*$", re.M)
_RULE_PATTERN = re.compile(r"[^*?\[\]]+\*?")


class BundleError(ValueError):
    """A bundle file violates OKF v0.2 conformance (§11)."""


@dataclass(frozen=True)
class Concept:
    """One OKF concept document."""

    id: str
    path: str
    type: str
    title: str
    description: str
    tags: tuple[str, ...]
    rule_ids: tuple[str, ...]
    frontmatter: Mapping[str, Any]
    body: str
    links: tuple[str, ...]

    @property
    def code(self) -> str:
        """Last path segment of the id, e.g. 'cc7.1' for 'controls/cc7.1'."""
        return self.id.rsplit("/", 1)[-1]

    @property
    def control_tags(self) -> tuple[str, ...]:
        """Tags naming a control, as written, e.g. ('cc7.1',) or ('iso42001:a.6',)."""
        return tuple(t for t in self.tags if _CONTROL_TAG.match(t))

    @property
    def control_keys(self) -> tuple[str, ...]:
        """Control tags as `framework:code` keys, e.g. ('soc2:cc7.1',)."""
        return tuple(control_key(t) for t in self.control_tags)

    @property
    def framework(self) -> str:
        """The control framework a control concept belongs to (`soc2` when unset)."""
        return str(self.frontmatter.get("framework") or DEFAULT_FRAMEWORK)

    @property
    def key(self) -> str:
        """Framework-qualified control key, e.g. 'iso42001:a.6'."""
        return f"{self.framework}:{self.code}"


@dataclass(frozen=True)
class Suppression:
    """A reviewed, expiring decision about one exact finding (Spec C)."""

    id: str
    kind: str
    tool: str
    rule_id: str
    target: str
    message_contains: str
    owner: str
    approved: date
    expires: date
    reason: str

    def matches(self, finding: Mapping[str, Any]) -> bool:
        """Exact tool, rule id, and target; `message_contains` narrows it when set. No wildcards."""
        return (
            (finding["tool"], finding["rule_id"], finding["target"]) == (self.tool, self.rule_id, self.target)
            and self.message_contains in finding["message"]
        )

    def active(self, today: date) -> bool:
        """In force from its approval date through its expiry date, inclusive."""
        return self.approved <= today <= self.expires


@dataclass(frozen=True)
class Bundle:
    """All concepts in a bundle, keyed by concept id."""

    concepts: Mapping[str, Concept]

    def of_type(self, *types: str) -> list[Concept]:
        """Concepts of the given type(s), sorted by id."""
        return sorted((c for c in self.concepts.values() if c.type in types), key=lambda c: c.id)

    def controls(self) -> list[Concept]:
        """Control concepts of every framework, sorted by id."""
        return self.of_type(*FRAMEWORK_TYPES.values())

    def control(self, key: str) -> Concept | None:
        """The control concept for `key` ('iso42001:a.6'; a bare 'cc7.1' means SOC 2), if the bundle has one."""
        key = control_key(key)
        return next((c for c in self.controls() if c.key == key), None)

    def by_rule(self, tool: str, rule_id: str) -> list[Concept]:
        """Concepts whose `rule_ids` declare coverage of this scanner rule (globs allowed)."""
        return [
            c
            for c in sorted(self.concepts.values(), key=lambda c: c.id)
            if any(_rule_matches(entry, tool, rule_id) for entry in c.rule_ids)
        ]

    def declaring(self, key: str) -> list[Concept]:
        """Concepts that declare `rule_ids` and carry the control tag for `key`, sorted by id."""
        key = control_key(key)
        return sorted(
            (c for c in self.concepts.values() if c.rule_ids and key in c.control_keys), key=lambda c: c.id
        )

    def crosswalk_pairs(self) -> list[tuple[str, str, str]]:
        """(crosswalk id, left control id, right control id) for each crosswalk line linking two controls."""
        control_ids = {c.id for c in self.controls()}
        pairs = []
        for cw in self.of_type(CROSSWALK_TYPE):
            for line in cw.body.splitlines():
                ids = [i for t in _LINK.findall(line) if (i := _resolve_link(t, cw.path)) in control_ids]
                if len(ids) == 2:
                    pairs.append((cw.id, ids[0], ids[1]))
        return pairs

    def suppressions(self) -> list[Suppression]:
        """Suppression concepts as typed records, sorted by id."""
        return [_suppression(c, self.section(c, "Reason") or "") for c in self.of_type(SUPPRESSION_TYPE)]

    def section(self, concept: Concept, heading: str) -> str | None:
        """Body text under `# heading`, up to the next level-1 heading."""
        matches = list(_H1.finditer(concept.body))
        for i, m in enumerate(matches):
            if m.group(1) == heading:
                end = matches[i + 1].start() if i + 1 < len(matches) else len(concept.body)
                return concept.body[m.end() : end].strip()
        return None


def control_key(tag: str) -> str:
    """Normalize a control tag to `framework:code`; a bare SOC 2 tag ('cc6.1') gets the `soc2:` prefix."""
    return tag if ":" in tag else f"{DEFAULT_FRAMEWORK}:{tag}"


def applies(control: Concept, context: Mapping[str, Any]) -> bool:
    """False when the control's `applies_when` names a context value that excludes it.

    A context key that is missing (no inventory) never excludes a control: unknown means assess it.
    """
    for field, allowed in (control.frontmatter.get("applies_when") or {}).items():
        if field in context and context[field] not in allowed:
            return False
    return True


def _rule_matches(entry: str, tool: str, rule_id: str) -> bool:
    entry_tool, _, pattern = entry.partition(":")
    return entry_tool == tool and fnmatchcase(rule_id, pattern)


def _resolve_link(target: str, concept_path: str) -> str | None:
    """Bundle-relative concept id for a markdown link, or None if it is not a concept link."""
    target = target.split("#", 1)[0]
    if "://" in target or target.startswith("mailto:") or not target.endswith(".md"):
        return None
    if target.startswith("/"):
        resolved = posixpath.normpath(target.lstrip("/"))
    else:
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(concept_path), target))
    if resolved.startswith("..") or posixpath.basename(resolved) in RESERVED:
        return None
    return resolved.removesuffix(".md")


def _string_list(rel_path: str, fm: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = fm.get(key, [])
    if not isinstance(value, list):
        raise BundleError(f"{rel_path}: '{key}' must be a YAML list")
    return tuple(str(v) for v in value)


def _check_grounding(rel_path: str, tags: tuple[str, ...], rule_ids: tuple[str, ...]) -> None:
    """Enforce the grounding rule: well-formed `<tool>:<prefix>[*]` entries and exactly one control tag."""
    for entry in rule_ids:
        tool, _, rule = entry.partition(":")
        if not tool or not _RULE_PATTERN.fullmatch(rule):
            raise BundleError(f"{rel_path}: rule id {entry!r} is not '<tool>:<literal prefix>[*]'")
    frameworks = [control_key(t).partition(":")[0] for t in tags if _CONTROL_TAG.match(t)]
    if rule_ids and (not frameworks or len(frameworks) != len(set(frameworks))):
        raise BundleError(f"{rel_path}: a concept declaring rule_ids needs exactly one control tag per framework")


def _check_control(rel_path: str, fm: Mapping[str, Any], type_: str) -> None:
    """A control's `framework` must be known and match its type; `applies_when` maps fields to lists."""
    framework = str(fm.get("framework") or DEFAULT_FRAMEWORK)
    if type_ in FRAMEWORK_TYPES.values() and FRAMEWORK_TYPES.get(framework) != type_:
        raise BundleError(f"{rel_path}: framework {framework!r} does not match type {type_!r}")
    applies_when = fm.get("applies_when", {})
    if not isinstance(applies_when, dict) or not all(isinstance(v, list) for v in applies_when.values()):
        raise BundleError(f"{rel_path}: 'applies_when' must map each field to a YAML list")


def _date(rel_path: str, value: Any, key: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as e:
        raise BundleError(f"{rel_path}: '{key}' must be an ISO date (YYYY-MM-DD)") from e


def _check_suppression(rel_path: str, fm: Mapping[str, Any], body: str) -> None:
    """A suppression names one exact finding, a kind, a human owner, and a window of at most 90 days."""
    if fm.get("kind") not in SUPPRESSION_KINDS:
        raise BundleError(f"{rel_path}: 'kind' must be one of {SUPPRESSION_KINDS}")
    finding = fm.get("finding")
    if not isinstance(finding, dict) or not all(str(finding.get(k) or "").strip() for k in ("tool", "rule_id", "target")):
        raise BundleError(f"{rel_path}: 'finding' needs tool, rule_id, and target")
    if any(ch in str(finding[k]) for k in ("tool", "rule_id", "target") for ch in "*?["):
        raise BundleError(f"{rel_path}: suppressions match one exact finding; no wildcards")
    if not str(fm.get("owner") or "").startswith("human:"):
        raise BundleError(f"{rel_path}: 'owner' must be a person (human:<name>)")
    approved, expires = _date(rel_path, fm.get("approved"), "approved"), _date(rel_path, fm.get("expires"), "expires")
    if not approved < expires <= approved + timedelta(days=MAX_SUPPRESSION_DAYS):
        raise BundleError(f"{rel_path}: 'expires' must fall within {MAX_SUPPRESSION_DAYS} days after 'approved'")
    if not re.search(r"^# Reason\s*\n\s*\S", body, re.M):
        raise BundleError(f"{rel_path}: a suppression needs a non-empty '# Reason' section")


def _suppression(concept: Concept, reason: str) -> Suppression:
    fm, finding = concept.frontmatter, concept.frontmatter["finding"]
    return Suppression(
        id=concept.id,
        kind=fm["kind"],
        tool=str(finding["tool"]),
        rule_id=str(finding["rule_id"]),
        target=str(finding["target"]),
        message_contains=str(finding.get("message_contains") or ""),
        owner=str(fm["owner"]),
        approved=_date(concept.path, fm["approved"], "approved"),
        expires=_date(concept.path, fm["expires"], "expires"),
        reason=reason,
    )


def _check_accepted_risks(bundle: Bundle) -> None:
    """An accepted risk must be on a finding that maps to an in-bundle control; a gap has no risk owner."""
    for s in bundle.suppressions():
        if s.kind != "accepted-risk":
            continue
        keys = {k for c in bundle.by_rule(s.tool, s.rule_id) for k in c.control_keys if bundle.control(k)}
        if not keys:
            raise BundleError(f"{s.id}: accepted-risk needs a finding that maps to a control; {s.tool}:{s.rule_id} is a gap")


def _parse(rel_path: str, text: str) -> Concept:
    m = _FRONTMATTER.match(text)
    if not m:
        raise BundleError(f"{rel_path}: missing YAML frontmatter")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise BundleError(f"{rel_path}: unparseable frontmatter: {e}") from e
    if not isinstance(fm, dict) or not str(fm.get("type") or "").strip():
        raise BundleError(f"{rel_path}: frontmatter has no non-empty 'type'")
    body = m.group(2)
    stem = rel_path.removesuffix(".md")
    tags = _string_list(rel_path, fm, "tags")
    rule_ids = _string_list(rel_path, fm, "rule_ids")
    _check_grounding(rel_path, tags, rule_ids)
    type_ = str(fm["type"]).strip()
    _check_control(rel_path, fm, type_)
    if type_ == SUPPRESSION_TYPE:
        _check_suppression(rel_path, fm, body)
    return Concept(
        id=stem,
        path=rel_path,
        type=type_,
        title=str(fm.get("title") or posixpath.basename(stem)),
        description=str(fm.get("description") or ""),
        tags=tags,
        rule_ids=rule_ids,
        frontmatter=fm,
        body=body,
        links=tuple(
            dict.fromkeys(
                link for t in _LINK.findall(body) if (link := _resolve_link(t, rel_path)) is not None
            )
        ),
    )


def load_bundle(root: Path) -> Bundle:
    """Parse every non-reserved .md under `root` into a Bundle."""
    concepts: dict[str, Concept] = {}
    for path in sorted(root.rglob("*.md")):
        if path.name in RESERVED:
            continue
        rel = path.relative_to(root).as_posix()
        concept = _parse(rel, path.read_text(encoding="utf-8"))
        concepts[concept.id] = concept
    bundle = Bundle(concepts=concepts)
    _check_accepted_risks(bundle)
    return bundle
```

- [ ] **Step 3: Run the suite.**

Run: `uv run pytest -q`
Expected: `370 passed`.

- [ ] **Step 4: Commit.**

```bash
git add .claude/skills/grc-continuous-compliance/scripts/okf_lib.py tests/test_suppressions.py tests/test_bundle_conformance.py
git commit -m "Add the Suppression concept with load-time validation" -m "Closes #<C1>"
```

---

## Task 2: map_findings: apply suppressions

**Files:**
- Modify: `.claude/skills/grc-continuous-compliance/scripts/map_findings.py` (full replacement below)
- Test: `tests/test_suppressions.py` (extend)

**Interfaces:**
- `map_findings(bundle, findings, context=None, today=None)`; CLI `--today YYYY-MM-DD`.
- When the bundle has any suppression, `mapping.json` gains:
  - `suppressed`: `[{finding, suppression, kind, controls, owner, expires, reason}]` for every finding an active suppression matched (both kinds);
  - `expired_suppressions`: ids whose `expires` is before `today`;
  - `unused_suppressions`: ids of active suppressions that matched nothing.
- A matched `false-positive` finding leaves `controls[*].findings` and `unmapped`. A matched `accepted-risk` finding stays in `controls[*].findings` with `"accepted": "<id>"`; statuses are computed as before, so the control stays `not-satisfied`.
- A bundle with no suppressions yields exactly `{"controls", "unmapped"}`.

- [ ] **Step 1: Write the failing tests.** Add `from map_findings import map_findings` to the imports of `tests/test_suppressions.py` and append:

```python


def _mapping(tmp_path: Path, today: date = IN_FORCE, **suppressions: str) -> dict:
    return map_findings(_bundle(tmp_path, **suppressions), FINDINGS, today=today)


# -- mapping ------------------------------------------------------------------------------------------


def test_false_positive_leaves_the_gap_list_but_stays_visible(tmp_path: Path) -> None:
    m = _mapping(tmp_path, fp=FALSE_POSITIVE)
    assert "CKV_TEST_99" not in [u["finding"]["rule_id"] for u in m["unmapped"]]
    (entry,) = m["suppressed"]
    assert (entry["kind"], entry["suppression"], entry["finding"]["rule_id"]) == (
        "false-positive", "suppressions/fp", "CKV_TEST_99"
    )


def test_accepted_risk_stays_on_its_control_and_keeps_the_status(tmp_path: Path) -> None:
    m = _mapping(tmp_path, accepted=ACCEPTED)
    entry = m["controls"]["soc2:cc7.1"]
    assert entry["status"] == "not-satisfied"
    assert [f.get("accepted") for f in entry["findings"]] == ["suppressions/accepted"]
    assert m["suppressed"][0]["controls"] == ["soc2:cc7.1"]


def test_a_false_positive_can_clear_a_control(tmp_path: Path) -> None:
    fp = _suppression("false-positive", "trivy", "CVE-2024-0001", "app/requirements.txt")
    assert _mapping(tmp_path, fp=fp)["controls"]["soc2:cc7.1"]["status"] == "no-violations-detected"


@pytest.mark.parametrize(
    ("today", "applies"),
    [(date(2026, 9, 27), False), (date(2026, 9, 28), True), (date(2026, 12, 27), True), (date(2026, 12, 28), False)],
)
def test_suppression_applies_from_approval_through_expiry(tmp_path: Path, today: date, applies: bool) -> None:
    m = _mapping(tmp_path, today=today, fp=FALSE_POSITIVE)
    assert bool(m["suppressed"]) is applies
    assert ("suppressions/fp" in m["expired_suppressions"]) is (today > date(2026, 12, 27))


def test_expired_suppression_puts_the_finding_back(tmp_path: Path) -> None:
    m = _mapping(tmp_path, today=date(2026, 12, 28), fp=FALSE_POSITIVE)
    assert "CKV_TEST_99" in [u["finding"]["rule_id"] for u in m["unmapped"]]
    assert m["expired_suppressions"] == ["suppressions/fp"]


def test_unused_suppression_is_reported(tmp_path: Path) -> None:
    stale = _suppression("false-positive", "checkov", "CKV_GONE", "app/Dockerfile")
    assert _mapping(tmp_path, stale=stale)["unused_suppressions"] == ["suppressions/stale"]


def test_message_contains_narrows_the_match(tmp_path: Path) -> None:
    narrow = _suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile",
                          extra="  message_contains: \"something else\"\n")
    m = _mapping(tmp_path, fp=narrow)
    assert m["suppressed"] == [] and m["unused_suppressions"] == ["suppressions/fp"]


def test_no_suppressions_means_no_new_keys() -> None:
    m = map_findings(load_bundle(FIXTURES / "bundle"), FINDINGS, today=IN_FORCE)
    assert set(m) == {"controls", "unmapped"}
```

Run: `uv run pytest tests/test_suppressions.py -q`
Expected: `TypeError: map_findings() got an unexpected keyword argument 'today'`.

- [ ] **Step 2: Replace `map_findings.py`.**

```python
"""Join normalized findings to in-bundle controls; never invent a mapping."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from okf_lib import GUARDRAIL_TYPES, SCANNER_TYPE, Bundle, Suppression, applies, load_bundle

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
        }
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--inventory", type=Path, default=Path("app/ai-inventory.yaml"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="date for suppression expiry")
    args = parser.parse_args()
    findings = json.loads((args.out / "findings.json").read_text(encoding="utf-8"))
    mapping = map_findings(load_bundle(args.knowledge), findings, load_context(args.inventory), args.today)
    (args.out / "mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the suite.** Expected: `381 passed`.

- [ ] **Step 4: Commit.**

```bash
git add .claude/skills/grc-continuous-compliance/scripts/map_findings.py tests/test_suppressions.py
git commit -m "Apply reviewed suppressions in map_findings, with expiry and unused detection" -m "Closes #<C2>"
```

---

## Task 3: to_oscal: accepted risks and false positives

**Files:**
- Modify: `.claude/skills/grc-continuous-compliance/scripts/to_oscal.py` (full replacement below), `docs/oscal-subset.md`
- Test: `tests/test_suppressions.py` (extend)

**Interfaces:**
- Each `accepted-risk` entry becomes a risk titled `Accepted risk: <tool> <rule_id>`, `status: deviation-approved`, with owner, expiry, reason, and suppression id in its description, related to the finding's observation. The control keeps its `not-satisfied` finding.
- Each `false-positive` finding keeps an observation (so the evidence is not lost) and is named in `remarks` ("Suppressed as false positives (reviewed; see the bundle): <ids>"); it is never a finding or a coverage-gap risk.

- [ ] **Step 1: Write the failing test.** Add `from oscal_schema import validate` and `from to_oscal import assessment_results` to the imports and append:

```python


# -- outputs ------------------------------------------------------------------------------------------


def test_oscal_records_accepted_risk_as_deviation_approved(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, accepted=ACCEPTED, fp=FALSE_POSITIVE)
    m = map_findings(bundle, FINDINGS, today=IN_FORCE)
    doc = assessment_results(bundle, m, NOW)
    validate(doc, "oscal_assessment-results_schema.json")
    (result,) = doc["assessment-results"]["results"]
    (accepted,) = [r for r in result["risks"] if r["status"] == "deviation-approved"]
    assert accepted["title"] == "Accepted risk: trivy CVE-2024-0001"
    assert "cc7.1" in {f["target"]["target-id"] for f in result["findings"]}
    assert "Suppressed as false positives (reviewed; see the bundle): suppressions/fp" in result["remarks"]
    assert any(o["title"] == "checkov CKV_TEST_99" for o in result["observations"])
    assert not any(r["title"] == "Coverage gap: checkov CKV_TEST_99" for r in result["risks"])
```

Run: `uv run pytest tests/test_suppressions.py -q`
Expected: 1 failure: no `deviation-approved` risk.

- [ ] **Step 2: Replace `to_oscal.py`.**

```python
"""Render a control mapping as OSCAL 1.2.3 component-definition + assessment-results (documented subset)."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from okf_lib import COMPONENT_TYPE, FRAMEWORK_TYPES, Bundle, Concept, load_bundle

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
NO_AP_HREF = "#assessment-plan-not-modeled"


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


def _observation(f: Json, now: str) -> Json:
    return {
        "uuid": _uuid("observation", _finding_key(f)),
        "title": f"{f['tool']} {f['rule_id']}",
        "description": f"{f['message']} ({f['target']}, severity {f['severity']})",
        "methods": ["TEST"],
        "collected": now,
    }


def _remarks(mapping: Json) -> str:
    """Controls without an OSCAL finding, stated so their absence is not read as a pass."""
    labels = {
        "no-violations-detected": "No violations detected by automated checks (not a control attestation)",
        "not-assessed": "Not assessed (no in-bundle scanner or policy)",
        "not-applicable": "Not applicable at the declared AI risk tier",
    }
    parts = []
    for status, label in labels.items():
        if keys := sorted(key for key, c in mapping["controls"].items() if c["status"] == status):
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


def assessment_results(bundle: Bundle, mapping: Json, now: str) -> Json:
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
        findings.append(
            {
                "uuid": _uuid("finding", key),
                "title": control.title if control else key,
                "description": f"{len(entry['findings'])} open finding(s).",
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
            "import-ap": {"href": NO_AP_HREF, "remarks": "Assessment plan not modeled in v1; see docs/oscal-subset.md."},
            "results": [result],
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--now", default=datetime.now(UTC).isoformat(timespec="seconds"))
    args = parser.parse_args()
    bundle = load_bundle(args.knowledge)
    mapping = json.loads((args.out / "mapping.json").read_text(encoding="utf-8"))
    oscal_dir = args.out / "oscal"
    oscal_dir.mkdir(parents=True, exist_ok=True)
    for name, doc in (
        ("component-definition.json", component_definition(bundle, args.now)),
        ("assessment-results.json", assessment_results(bundle, mapping, args.now)),
    ):
        (oscal_dir / name).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Document it.** Apply to `docs/oscal-subset.md`:

```diff
diff --git a/docs/oscal-subset.md b/docs/oscal-subset.md
index e8c6ded..d1826a3 100644
--- a/docs/oscal-subset.md
+++ b/docs/oscal-subset.md
@@ -22,8 +22,8 @@ subset, not a complete OSCAL implementation.
 | `results[0].reviewed-controls` | one `control-selection` per framework, described by the framework's source title; includes every control whose status is not `not-assessed` or `not-applicable` |
 | `results[0].observations[]` | one per scanner finding; `methods: [TEST]` |
 | `results[0].findings[]` | one per control with open violations; `target.status.state` is always `not-satisfied` |
-| `results[0].risks[]` | one per unmapped finding, titled "Coverage gap: …", `status: open` |
-| `results[0].remarks` | lists controls with no violations detected, controls not assessed, and controls not applicable at the declared AI risk tier (by `framework:code` key) |
+| `results[0].risks[]` | one per unmapped finding, titled "Coverage gap: …", `status: open`; and one per accepted-risk suppression, titled "Accepted risk: …", `status: deviation-approved`, with the owner, expiry, and reason in its description |
+| `results[0].remarks` | lists controls with no violations detected, controls not assessed, controls not applicable at the declared AI risk tier (by `framework:code` key), and false-positive suppressions (by suppression id) |
 
 ## Deliberately not modeled
 
@@ -40,3 +40,7 @@ subset, not a complete OSCAL implementation.
   and `control-id` values are the Annex A group ids (`a.6`).
 - `not-applicable` as a finding: a control excluded by the declared AI risk tier
   is not assessed, so it is named in `remarks`, never reported as a pass.
+- A suppressed finding as a pass: a false positive keeps its observation and is
+  named in `remarks`; an accepted risk keeps its control's `not-satisfied`
+  finding and adds a `deviation-approved` risk. OSCAL findings have only
+  `satisfied` and `not-satisfied`, so there is no separate accepted state.
```

- [ ] **Step 4: Run the suite.** Expected: `382 passed`.

- [ ] **Step 5: Commit.**

```bash
git add .claude/skills/grc-continuous-compliance/scripts/to_oscal.py docs/oscal-subset.md tests/test_suppressions.py
git commit -m "Record accepted risks as deviation-approved OSCAL risks and name false positives in remarks" -m "Closes #<C3>"
```

---

## Task 4: render_report: never hidden

**Files:**
- Modify: `.claude/skills/grc-continuous-compliance/scripts/render_report.py` (full replacement below)
- Test: `tests/test_suppressions.py` (extend)

**Interfaces:**
- Accepted findings are marked inline: `— **accepted risk** (`<id>`)`.
- Risk posture: accepted findings are not counted as open; controls are counted as "with open findings"; one clause adds "N accepted risk(s) and M false positive(s) suppressed after review."
- New sections after **Coverage gaps**, each only when non-empty: **Suppressed** (table: kind, finding, owner, expiry, reason as plain text), **Expired suppressions**, **Unused suppressions**.
- Reasons render as one table cell: links become their text (bundle-relative paths would break in `out/`), `|` is escaped.

- [ ] **Step 1: Write the failing tests.** Add `from render_report import render_report` to the imports and append:

```python


def test_report_marks_accepted_findings_and_lists_suppressions(tmp_path: Path) -> None:
    stale = _suppression("false-positive", "checkov", "CKV_GONE", "app/Dockerfile")
    bundle = _bundle(tmp_path, accepted=ACCEPTED, fp=FALSE_POSITIVE, stale=stale)
    report = render_report(bundle, map_findings(bundle, FINDINGS, today=IN_FORCE), NOW)
    assert "— **accepted risk** (`suppressions/accepted`)" in report
    assert "1 accepted risk and 1 false positive suppressed after review." in report
    assert "2 open findings across 1 of 4 controls" in report
    assert "| false-positive | `checkov` `CKV_TEST_99` — `app/Dockerfile` | human:reviewer | 2026-12-27 |" in report
    assert "## Unused suppressions" in report and "## Expired suppressions" not in report


def test_reason_renders_as_one_plain_table_cell(tmp_path: Path) -> None:
    fp = _suppression("false-positive", "checkov", "CKV_TEST_99", "app/Dockerfile",
                      reason="See [CC7.1](../controls/cc7.1.md) | and\nmore.")
    bundle = _bundle(tmp_path, fp=fp)
    report = render_report(bundle, map_findings(bundle, FINDINGS, today=IN_FORCE), NOW)
    assert "| See CC7.1 \\| and more. |" in report
```

Run: `uv run pytest tests/test_suppressions.py -q`
Expected: 2 failures (no marker, no sections).

- [ ] **Step 2: Replace `render_report.py`.**

```python
"""Render the control mapping as an auditor-facing markdown report."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from okf_lib import FRAMEWORK_TITLES, Bundle, load_bundle

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
    open_findings = not_satisfied = not_assessed = not_applicable = clean = 0
    for _key, entry in controls:
        status = entry["status"]
        if status == "not-applicable":
            not_applicable += 1
            continue
        if status == "not-assessed":
            not_assessed += 1
        elif status == "not-satisfied":
            # counts controls with open findings; a control whose findings are all accepted risks does not
            not_satisfied += any(not f.get("accepted") for f in entry["findings"])
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
        f"{clean} {clean_clause} no violations. {not_assessed} not assessed.{na_clause} "
        f"{len(unmapped)} {gaps_word} to triage.{suppressed_clause}",
        "",
    ]


def _table_text(text: str) -> str:
    """Bundle prose as one table cell: links become their text (bundle-relative paths break here), `|` escaped."""
    plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", " ".join(text.split()))
    return plain.replace("|", "\\|")


def _suppression_sections(mapping: Json) -> list[str]:
    """Suppressed, expired, and unused suppressions; each section appears only when it has entries."""
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
    if expired := mapping.get("expired_suppressions"):
        lines += ["", "## Expired suppressions", "", "No longer applied; their findings count again. Renew or remove.", ""]
        lines += [f"- `{sid}`" for sid in expired]
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
    for key in not_assessed:
        lines.append(f"- {_title(bundle, key)}: no in-bundle scanner or policy evidences this control.")
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--now", default=datetime.now(UTC).isoformat(timespec="seconds"))
    args = parser.parse_args()
    mapping = json.loads((args.out / "mapping.json").read_text(encoding="utf-8"))
    narratives_path, ledger = args.out / "narratives.json", args.out / "llm-usage.jsonl"
    narratives = json.loads(narratives_path.read_text(encoding="utf-8")) if narratives_path.is_file() else {}
    usage = [json.loads(ln) for ln in ledger.read_text(encoding="utf-8").splitlines()] if ledger.is_file() else []
    last_run = [e for e in usage if usage and e["run_id"] == usage[-1]["run_id"]]
    report = render_report(load_bundle(args.knowledge), mapping, args.now, narratives, last_run)
    (args.out / "report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the suite.** Expected: `384 passed`; the golden report is unchanged.

- [ ] **Step 4: Commit.**

```bash
git add .claude/skills/grc-continuous-compliance/scripts/render_report.py tests/test_suppressions.py
git commit -m "Show suppressed, expired, and unused suppressions in the report" -m "Closes #<C4>"
```

---

## Task 5: digest: open findings only

**Files:**
- Modify: `.claude/skills/grc-continuous-compliance/scripts/digest.py` (full replacement below)
- Test: `tests/test_suppressions.py` (extend)

**Interfaces:**
- `scan_digest` counts only open findings per control; `accepted_risks` appears on a control only when non-zero, and `suppressed_false_positives` at the top level only when non-zero, so narrate never calls an accepted or suppressed finding open, and existing digests (and the recorded replay fixtures) are unchanged.

- [ ] **Step 1: Write the failing test.** Add `from digest import scan_digest` to the imports and append:

```python


def test_digest_counts_accepted_and_false_positives_apart(tmp_path: Path) -> None:
    m = _mapping(tmp_path, accepted=ACCEPTED, fp=FALSE_POSITIVE)
    d = scan_digest(m)
    assert d["controls"]["soc2:cc7.1"] == {"status": "not-satisfied", "findings": 0, "by_severity": {},
                                           "accepted_risks": 1}
    assert d["suppressed_false_positives"] == 1
    assert "accepted_risks" not in d["controls"]["soc2:cc6.1"]
```

Run: `uv run pytest tests/test_suppressions.py -q`
Expected: 1 failure (accepted counted as open).

- [ ] **Step 2: Replace `digest.py`.**

```python
"""Small, stable digests of the bundle and of a scan: the only input the LLM step sees."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from okf_lib import FRAMEWORK_SCOPES, Bundle

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
```

- [ ] **Step 3: Run the suite.** Expected: `385 passed`, including `test_llm_recorded.py` (the narrate and triage requests are byte-identical).

- [ ] **Step 4: Commit.**

```bash
git add .claude/skills/grc-continuous-compliance/scripts/digest.py tests/test_suppressions.py
git commit -m "Count only open findings in the LLM digest" -m "Closes #<C5>"
```

---

## Task 6: Sample suppressions, seeds, integration — HUMAN GATE

**Files:**
- Create: `knowledge/suppressions/{index,trivy-trusted-registry,django-cve-2023-31047}.md`
- Modify: `knowledge/index.md`, `knowledge/log.md`, `app/SEEDED.yaml`, `tests/test_seeded_ledger.py`, `tests/test_integration.py`

**The two samples, chosen from the real scan:**
- **False positive:** `trivy:KSV-0125` on `app/k8s/deployment.yaml`, "restrict container images to trusted registries". The image is `ghcr.io/example/widgets-api`, the project's own registry, which Trivy's built-in list does not include. It fires once, is not a seeded issue, and seed S2 stays an honest gap.
- **Accepted risk:** `trivy:CVE-2023-31047` on `app/requirements.txt` (seed S7), a multiple-file-upload validation bypass in Django; the sample API has no upload field. The finding stays on CC7.1, so S7 still holds, now marked accepted.

- [ ] **Step 1: Add the concepts** (without `verified`; that is the gate).

`knowledge/suppressions/index.md`:

```markdown
# Suppressions

Reviewed, time-limited decisions about one exact finding each. A suppression
changes how a finding counts, never whether it is shown: every report lists
suppressed, expired, and unused suppressions.

* [Own registry flagged as untrusted](trivy-trusted-registry.md) - Trivy's default trusted-registry list does not include the project's own registry.
* [Django multiple-file upload bypass (CVE-2023-31047)](django-cve-2023-31047.md) - Accepted until the scheduled upgrade; the sample API has no file uploads.
```

`knowledge/suppressions/trivy-trusted-registry.md`:

```markdown
---
type: Suppression
title: Own registry flagged as untrusted
description: Trivy's default trusted-registry list does not include the project's own registry.
kind: false-positive
finding:
  tool: trivy
  rule_id: KSV-0125
  target: app/k8s/deployment.yaml
  message_contains: "Container api in deployment widgets-api"
owner: human:cdevarenne
approved: "2026-09-28"
expires: "2026-12-27"
tags: [suppression, kubernetes]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Reason

The deployment pulls `ghcr.io/example/widgets-api`, the project's own registry.
Trivy judges KSV-0125 against its built-in list of trusted registries, which
does not include it, so the finding says nothing about this image's provenance.

# Renewal

Remove this suppression once the scan passes the project's registry to Trivy as
trusted; until then, renew it only after re-checking the image source.
```

`knowledge/suppressions/django-cve-2023-31047.md`:

```markdown
---
type: Suppression
title: Django multiple-file upload bypass (CVE-2023-31047)
description: Accepted until the scheduled upgrade; the sample API has no file uploads.
kind: accepted-risk
finding:
  tool: trivy
  rule_id: CVE-2023-31047
  target: app/requirements.txt
owner: human:cdevarenne
approved: "2026-09-28"
expires: "2026-12-27"
tags: [suppression, django, cc7.1]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Reason

CVE-2023-31047 lets a single form field upload several files and bypass the
validation meant for one. The sample API exposes no file-upload field: widgets
carry a name and a text description only. The vulnerability stays on
[CC7.1 — Vulnerability Detection](../controls/cc7.1.md) as a known, accepted
risk until the Django upgrade lands.

# Compensating control

No endpoint accepts file uploads, and a new upload field would be caught in code
review. The Django pin is scheduled for upgrade to a fixed 4.2.x release before
this acceptance expires.
```

- [ ] **Step 2: Index and log.**

```diff
diff --git a/knowledge/index.md b/knowledge/index.md
index 65f3420..fce462a 100644
--- a/knowledge/index.md
+++ b/knowledge/index.md
@@ -15,5 +15,6 @@ invent a mapping.
 * [Stack](stack/) - the sample app and its infrastructure
 * [Policies](policies/) - guardrails (Rego, Semgrep) and the scanner rules that detect each
 * [Scanners](scanners/) - DevSecOps tools and the controls they evidence
+* [Suppressions](suppressions/) - reviewed, expiring false positives and accepted risks; never hidden
 * [AI system inventory](ai-inventory.md) - the declared AI risk tier that decides which controls apply
 * [OSCAL output](oscal/component-definition.md) - the machine-readable output target
diff --git a/knowledge/log.md b/knowledge/log.md
index 3e719b2..0f88662 100644
--- a/knowledge/log.md
+++ b/knowledge/log.md
@@ -9,3 +9,4 @@
 * **Update**: Added ISO/IEC 42001 Annex A (A.4–A.9) and EU AI Act (Art. 9, 10, 12–15, 50) controls, two crosswalks, five AI guardrails, the AI assistant component, and the AI inventory reference. SOC 2 controls gain `framework: soc2`.
 * **Update**: Human review of the AI governance concepts; verified recorded.
 * **Update**: Added the GRC agent LLM step as a stack component (self-evidence).
+* **Update**: Added the suppressions folder: one false positive (Trivy KSV-0125, own registry) and one accepted risk (CVE-2023-31047), each expiring 2026-12-27.
```

- [ ] **Step 3: Seeds and tests.** A seed can now expect `suppressed: <kind>` (with `unsuppressed` and `suppression` saying where it lands after expiry) or `accepted: <id>` alongside `controls`:

```diff
diff --git a/app/SEEDED.yaml b/app/SEEDED.yaml
index 8709b52..940803b 100644
--- a/app/SEEDED.yaml
+++ b/app/SEEDED.yaml
@@ -1,6 +1,9 @@
 # INTENTIONALLY VULNERABLE SCAN TARGET — DO NOT DEPLOY.
 # Each seeded issue, the scanner rules observed to detect it, and the expected outcome:
-# `controls` lists every control key the finding must land on; `gap` names the coverage-gap reason.
+# `controls` lists every control key the finding must land on; `gap` names the coverage-gap reason;
+# `suppressed` names the suppression kind of a reviewed false positive; `accepted` names the suppression
+# id of an accepted risk, which stays on its controls. Suppressions expire: once expired, the finding
+# lands as it would without one (asserted by tests/test_integration.py).
 # Asserted by tests/test_integration.py (make test-integration).
 - id: S1
   file: app/Dockerfile
@@ -36,7 +39,7 @@
   file: app/requirements.txt
   issue: Django 4.2.0 has known CVEs
   detected_by: ["trivy:CVE-2023-31047"]
-  expect: {controls: [soc2:cc7.1]}
+  expect: {controls: [soc2:cc7.1], accepted: suppressions/django-cve-2023-31047}
 - id: AI-1
   file: app/assistant/views.py
   issue: the prompt (with user input) is written to the log in clear text
@@ -67,3 +70,8 @@
   issue: AI output is written to a record with no human-review flag (no rule declared)
   detected_by: ["semgrep:llm-output-unreviewed-write"]
   expect: {gap: no-rule-match}
+- id: SUP-1
+  file: app/k8s/deployment.yaml
+  issue: image from the project's own registry flagged as untrusted (a reviewed false positive)
+  detected_by: ["trivy:KSV-0125"]
+  expect: {suppressed: false-positive, unsuppressed: {gap: no-rule-match}, suppression: suppressions/trivy-trusted-registry}
diff --git a/tests/test_integration.py b/tests/test_integration.py
index edbc893..d382a3d 100644
--- a/tests/test_integration.py
+++ b/tests/test_integration.py
@@ -33,18 +33,50 @@ def _located(mapping: dict, tool: str, rule_id: str, file: str) -> set[str]:
         for u in mapping["unmapped"]
         if (u["finding"]["tool"], u["finding"]["rule_id"], u["finding"]["target"]) == (tool, rule_id, file)
     }
+    hits |= {
+        f"suppressed:{s['kind']}"
+        for s in mapping.get("suppressed", [])
+        if s["kind"] == "false-positive"
+        and (s["finding"]["tool"], s["finding"]["rule_id"], s["finding"]["target"]) == (tool, rule_id, file)
+    }
     return hits
 
 
 SEEDED = yaml.safe_load((ROOT / "app" / "SEEDED.yaml").read_text())
 
 
+def _expected(seed: dict, mapping: dict) -> set[str]:
+    """Where a seed's findings must land today; an expired suppression lands them as if it did not exist."""
+    expect = seed["expect"]
+    if "suppressed" in expect:
+        if expect["suppression"] in mapping.get("expired_suppressions", []):
+            expect = expect["unsuppressed"]
+        else:
+            return {f"suppressed:{expect['suppressed']}"}
+    return set(expect.get("controls", [])) or {f"gap:{expect['gap']}"}
+
+
 @pytest.mark.parametrize("seed", SEEDED, ids=lambda s: s["id"])
 def test_seeded_issue_lands_where_expected(mapping: dict, seed: dict) -> None:
-    expected = set(seed["expect"].get("controls", [])) or {f"gap:{seed['expect']['gap']}"}
     for detector in seed["detected_by"]:
         tool, rule_id = detector.split(":", 1)
-        assert _located(mapping, tool, rule_id, seed["file"]) == expected, f"{seed['id']} {detector}"
+        assert _located(mapping, tool, rule_id, seed["file"]) == _expected(seed, mapping), f"{seed['id']} {detector}"
+
+
+@pytest.mark.parametrize("seed", [s for s in SEEDED if "accepted" in s["expect"]], ids=lambda s: s["id"])
+def test_accepted_risk_is_marked_while_in_force(mapping: dict, seed: dict) -> None:
+    sid = seed["expect"]["accepted"]
+    marks = {
+        f.get("accepted")
+        for entry in mapping["controls"].values()
+        for f in entry["findings"]
+        if (f["tool"], f["rule_id"], f["target"]) == (*seed["detected_by"][0].split(":", 1), seed["file"])
+    }
+    assert marks == ({None} if sid in mapping.get("expired_suppressions", []) else {sid})
+
+
+def test_no_suppression_is_unused(mapping: dict) -> None:
+    assert mapping.get("unused_suppressions", []) == []
 
 
 def test_outputs_exist_and_oscal_validates(mapping: dict) -> None:
diff --git a/tests/test_seeded_ledger.py b/tests/test_seeded_ledger.py
index 30a21ef..1fdae39 100644
--- a/tests/test_seeded_ledger.py
+++ b/tests/test_seeded_ledger.py
@@ -23,6 +23,12 @@ def test_entry_is_well_formed(seed: dict) -> None:
     for detector in seed["detected_by"]:
         tool, _, rule = detector.partition(":")
         assert tool in TOOLS and rule
-    assert len(seed["expect"]) == 1 and set(seed["expect"]) <= {"controls", "gap"}
+    outcome = set(seed["expect"]) & {"controls", "gap", "suppressed"}
+    assert len(outcome) == 1, f"{seed['id']}: exactly one of controls, gap, suppressed"
+    assert set(seed["expect"]) <= {"controls", "gap", "suppressed", "accepted", "unsuppressed", "suppression"}
+    if "suppressed" in seed["expect"]:
+        assert {"unsuppressed", "suppression"} <= set(seed["expect"]), f"{seed['id']}: say where it lands once expired"
+    if "accepted" in seed["expect"]:
+        assert "controls" in seed["expect"], f"{seed['id']}: an accepted risk stays on its controls"
     for key in seed["expect"].get("controls", []):
         assert ":" in key, f"{seed['id']}: control {key!r} is not a framework:code key"
```

The integration expectations follow the calendar: while a suppression is in force its seed must be suppressed or marked; once it expires, the same test expects the finding back where it would land without it. An expired sample therefore shows up as an expired suppression in the report, not as a failing test.

- [ ] **Step 4: Run.**

Run: `uv run pytest -q`
Expected: exactly **2 failures**, `test_every_concept_is_human_verified[suppressions/…]` for the two new concepts.

Run: `make test-integration`
Expected: `22 passed`.

- [ ] **Step 5: STOP. Hand off.** The maintainer reviews each suppression (is it really a false positive, is the risk really acceptable, are the owner and dates right), adds a `verified` entry to both, and commits:

```bash
git add knowledge app/SEEDED.yaml tests/test_seeded_ledger.py tests/test_integration.py
git commit -m "Add two reviewed sample suppressions and assert them end to end" -m "Closes #<C6>"
```

---

## Task 7: README and SKILL.md (docs only)

**Files:**
- Modify: `README.md`, `.claude/skills/grc-continuous-compliance/SKILL.md`

- [ ] **Step 1: Apply:**

```diff
diff --git a/.claude/skills/grc-continuous-compliance/SKILL.md b/.claude/skills/grc-continuous-compliance/SKILL.md
index b320479..8a26ca3 100644
--- a/.claude/skills/grc-continuous-compliance/SKILL.md
+++ b/.claude/skills/grc-continuous-compliance/SKILL.md
@@ -48,6 +48,11 @@ description: >
    coverage-gap rule. Present the proposals for human review as `rule_ids`
    additions to the relevant guardrail concept. Never apply them, and do not
    edit `knowledge/` unasked.
+6. **Suppressions are a person's decision.** If a finding looks like a false
+   positive or a risk to accept, say so and draft the suppression for review
+   (one exact finding, owner, reason, expiry within 90 days). Never add, renew,
+   or extend a suppression unasked, and always report the Suppressed, Expired,
+   and Unused sections of `out/report.md`.
 
 ## Scope
 
diff --git a/README.md b/README.md
index 9224e8c..d1f3122 100644
--- a/README.md
+++ b/README.md
@@ -42,6 +42,27 @@ This is generated by `make examples` (which runs `make scan` against the sample
 CVE counts change as Trivy's vulnerability database updates.
 
 
+## Suppressions
+
+A suppression is a reviewed decision about one exact finding, stored in
+[`knowledge/suppressions/`](knowledge/suppressions/) with an owner, a reason,
+and an expiry at most 90 days after approval. It changes how the finding
+counts, never whether it is shown:
+
+- **`false-positive`**: the finding no longer counts toward its control or the
+  coverage-gap list, and is listed under **Suppressed** in the report and in the
+  OSCAL `remarks`.
+- **`accepted-risk`**: the finding stays on its control, which stays
+  `not-satisfied`; it is marked accepted in the report and recorded in OSCAL as
+  a risk with status `deviation-approved`.
+
+An expired suppression stops applying (the finding counts again and the report
+lists it under **Expired suppressions**); one that matches no finding is listed
+under **Unused suppressions**. Suppressions match on tool, rule id, target, and
+optionally a message substring; there are no wildcards, and an accepted risk on
+a coverage gap is rejected when the bundle loads. `map_findings.py --today`
+sets the date used for expiry.
+
 ## LLM step and cost
 
 The scan, the mapping, OSCAL, and every number in the report are deterministic.
@@ -223,9 +244,11 @@ Built with an AI coding agent under a written process; the record is in the repo
 - **Evidence, not attestation.** A control with no violations is reported as
   `no-violations-detected`, never `satisfied`. Automated scans evidence a SOC 2
   criterion; they do not attest it.
-- **No suppression workflow.** Scanner-native inline skips (e.g. `checkov:skip`)
-  are honored by the scanners themselves; there is no triage layer for false
-  positives, so they appear as findings or coverage gaps.
+- **Suppressions are exact and short-lived by design.** Each one matches a
+  single finding, lasts at most 90 days, and needs a human review; there are no
+  wildcard or bulk suppressions. Scanner-native inline skips (e.g.
+  `checkov:skip`) are still honored by the scanners themselves and bypass this
+  record.
 - **Static manifests only.** Helm or Kustomize output is not rendered before
   scanning.
 - **Sized for the sample app.** Scanner JSON is read in memory, and the
```

- [ ] **Step 2: Refresh the example.** Run `make scan`, then `LLM_MODE=anthropic make narrate` if the narratives should be current, and copy `out/report.md` to `examples/report.md`.

- [ ] **Step 3: Run.** `uv run pytest -q` stays green.

- [ ] **Step 4: Commit.**

```bash
git add README.md .claude/skills/grc-continuous-compliance/SKILL.md examples/report.md
git commit -m "Document suppressions in the README and the skill" -m "Docs only; no new tests." -m "Closes #<C7>"
```

---

## Done when (spec §2)

| Spec criterion | Where it is proven |
|---|---|
| 1. False positive leaves status and gaps, listed with owner, reason, expiry | `test_false_positive_leaves_the_gap_list_but_stays_visible`, `test_report_marks_accepted_findings_and_lists_suppressions` |
| 2. Accepted risk keeps `not-satisfied`, marked, OSCAL `deviation-approved` | `test_accepted_risk_stays_on_its_control_and_keeps_the_status`, `test_oscal_records_accepted_risk_as_deviation_approved` |
| 3. Expired suppression stops applying and is listed | `test_suppression_applies_from_approval_through_expiry`, `test_expired_suppression_puts_the_finding_back` |
| 4. Unused suppression is listed | `test_unused_suppression_is_reported`, `test_no_suppression_is_unused` (integration) |
| 5. Conformance rejects bad suppressions; review required | `test_malformed_suppressions_are_rejected`, `test_every_concept_is_human_verified` |
| 6. OSCAL validates; unit and integration pass | Tasks 3–6 |
