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
EXPIRY_WARNING_DAYS = 14  # an active suppression this close to expiry is flagged for renewal or removal
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
