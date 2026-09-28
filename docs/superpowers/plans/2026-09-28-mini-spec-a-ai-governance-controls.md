# Mini Spec A — AI Governance Controls: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `make scan` finds six seeded AI-governance issues in a new `app/assistant/` feature and maps each one, through `rule_ids` only, to ISO/IEC 42001 Annex A and EU AI Act controls; high-risk articles report `not-applicable` at the declared `limited` tier; one seed stays an honest coverage gap; OSCAL carries one `control-implementation` per framework source; the report has one section per framework plus a crosswalk table.

**Architecture:** Controls become framework-qualified (`soc2:cc6.1`, `iso42001:a.6`, `eu-ai-act:art-50`). `okf_lib` learns a `framework` field, an `applies_when` predicate, and crosswalk parsing. `map_findings` reads the declared risk tier from `app/ai-inventory.yaml` and marks excluded controls `not-applicable` before the finding loop. `to_oscal` and `render_report` group by framework. Two new scanners are not needed: five new Semgrep rules and one Rego policy do the detecting. The grounding rule is unchanged; it is widened from "exactly one control tag" to "exactly one control tag **per framework**".

**Tech Stack:** unchanged from v1 — Python 3.14 (uv), PyYAML, pytest, jsonschema; Semgrep 1.178.0, Trivy 0.74.0, Checkov 3.3.19, Conftest 0.70.1; OSCAL 1.2.3.

**Spec:** `docs/superpowers/specs/2026-09-25-mini-spec-a-ai-governance-controls.md`

**Provenance:** every code block in this plan was run in a prototype on 2026-09-28 against the pinned tools. Tasks 1 and 2 were replayed in isolation on a clean checkout: Task 1 left 154 unit tests green, Task 2 left 168 unit tests and all 9 v1 integration tests green. The complete prototype (all tasks) ran `make test` green (Rego and Semgrep rule tests included) and `make test-integration` green with 19 integration tests; the only unit failures were the 22 expected `not human-verified` failures that Task 6 (the human gate) resolves. The real scan produced exactly the six AI findings below and no other new findings.

## Global Constraints

- Everything in the v1 plan's Global Constraints still holds (Python `>=3.14`, PyYAML-only runtime, pinned tools from `tools.lock`, relative bundle links, type hints and docstrings, public clean-room content).
- **Commits:** trunk-based on `main`; authored by the repo-local identity (`cdevarenne`, no-reply email). **Never add a `Co-Authored-By` trailer.** Short subject, `Closes #N` body line. Every commit ships tests; docs-only commits say so.
- **Clean-room (spec §3):** ISO/IEC 42001 is copyrighted. Concepts carry clause ids and group names only, with intents written in our own words. Never paste Annex A text. EU AI Act articles are cited by number, paraphrased, and linked to EUR-Lex. NIST AI RMF is a crosswalk link only.
- **`app/` stays intentionally vulnerable.** Do not "fix" seeded issues. The API key in `app/assistant/settings.py` is the literal placeholder `placeholder-not-a-real-key`; never commit anything that looks like a real key.
- The grounding rule does not change: a finding reaches a control only through a `rule_ids` declaration. Crosswalk links are navigation and never move a finding or a status.

## Decisions this plan makes (spec review notes)

| # | Spec text | Decision | Why |
|---|---|---|---|
| D1 | §5 "AI-3 maps to Art. 15 … Recommendation: (b)" | **(b):** AI-3 maps to `iso42001:a.6` only; a `risk_tier: high` unit fixture exercises a high-risk article instead. | Art. 15 is a high-risk obligation; at `limited` it would only ever show `not-applicable`. |
| D2 | §4 AI-1 → "AI Act Art. 10, Art. 12" | AI-1 maps to `iso42001:a.7` and `eu-ai-act:art-12` only. Art. 10 is linked from the crosswalk. | The widened grounding rule allows one control tag **per framework** on a rule-declaring concept, so one guardrail cannot claim two AI Act articles. Art. 12 (record-keeping) is the direct fit for a logging defect. |
| D3 | §6 `conftest:ai-inventory-complete` | The rule id is `conftest:ai_inventory_complete`. | Conftest rule ids are the Rego package name, and package names cannot contain `-`. v1 ids follow the same form (`deny_latest_tag`). |
| D4 | §4 AI-6 "no rule declared" | AI-6 is detected by a sixth Semgrep rule, `llm-output-unreviewed-write`, that no concept declares. | A coverage gap needs a finding. The rule exists and is tested; the bundle deliberately does not claim it. |
| D5 | §7 "Key controls by `framework:code`" | **Every** control, SOC 2 included, is keyed `framework:code` in `mapping.json` (`soc2:cc6.1`). SOC 2 tags in the bundle stay bare (`cc6.1`) and normalize to `soc2:`. OSCAL `control-id`s stay bare codes inside each framework's source. | One key shape for every consumer (report, OSCAL, Spec B's narratives). Bare SOC 2 tags avoid churn in 18 human-verified concepts. OSCAL tokens cannot contain `:`. |
| D6 | §4 "`settings.py`" | The key lives in `app/assistant/settings.py`. | The sample app has no project-level `settings.py`. |

## Task order and parallelism

Task 1 (`okf_lib`) comes first; Task 2 moves every consumer of `mapping.json` to the new keys in one commit, so no intermediate commit has a half-migrated pipeline. **Tasks 3 and 4 are independent of Tasks 1–2 and of each other** and can run as parallel subagents. **Task 5 depends on Tasks 1–4. Task 6 is a human gate:** an executing agent must stop after Task 5 and hand off to the repo owner, because the conformance test requires a human `verified` entry on every concept and ISO clause ids must be checked against a licensed copy. Tasks 7 and 8 follow the gate.

## Task 0: Tracking issues (no commit)

- [ ] **Step 1: Create one GitHub issue per task.** Note the next free issue number `N` first; Task k becomes issue `N+k-1`. Use those numbers in each task's `Closes #` line.

```bash
PLAN=docs/superpowers/plans/2026-09-28-mini-spec-a-ai-governance-controls.md
gh issue create --title "A1: okf_lib: frameworks, control keys, applicability, crosswalks" --body "Spec A. See $PLAN, Task 1."
gh issue create --title "A2: Framework keys and applicability across map, OSCAL, report" --body "Spec A. See $PLAN, Task 2."
gh issue create --title "A3: Sample AI assistant feature and seeds AI-1..AI-6" --body "Spec A. See $PLAN, Task 3."
gh issue create --title "A4: AI governance rules: Semgrep and Rego" --body "Spec A. See $PLAN, Task 4."
gh issue create --title "A5: ISO 42001 / EU AI Act concepts and crosswalks (draft)" --body "Spec A. See $PLAN, Task 5."
gh issue create --title "A6: Human review of the AI governance concepts" --body "Spec A gate. See $PLAN, Task 6."
gh issue create --title "A7: End-to-end integration and refreshed example" --body "Spec A. See $PLAN, Task 7."
gh issue create --title "A8: README: AI governance and limits" --body "Spec A. See $PLAN, Task 8."
```

- [ ] **Step 2: Verify.** Run `gh issue list --limit 20`. Expected: the eight new issues, open.

---

## Task 1: okf_lib: frameworks, control keys, applicability, crosswalks

**Files:**
- Modify: `.claude/skills/grc-continuous-compliance/scripts/okf_lib.py` (full replacement below)
- Modify: `knowledge/controls/cc6.1.md`, `cc6.6.md`, `cc7.1.md`, `cc7.2.md`, `cc8.1.md` (add `framework: soc2`)
- Modify: `tests/test_bundle_conformance.py`
- Create: `tests/fixtures/ai_bundle/**`, `tests/fixtures/ai_findings.json`
- Test: `tests/test_multi_framework.py`, `tests/test_applicability.py`

**Interfaces:**
- Produces: `FRAMEWORK_TYPES` (`{"soc2": "SOC 2 Control", "iso42001": "ISO/IEC 42001 Control", "eu-ai-act": "EU AI Act Article"}`), `FRAMEWORK_TITLES`, `CROSSWALK_TYPE = "Crosswalk"`; `control_key(tag) -> str`; `applies(control, context) -> bool`; `Concept.framework`, `Concept.key`, `Concept.control_keys`; `Bundle.control(key)` and `Bundle.declaring(key)` accept `framework:code` or a bare SOC 2 code; `Bundle.crosswalk_pairs() -> list[(crosswalk_id, left_id, right_id)]`.
- Consumes: nothing new. `map_findings`, `to_oscal`, and `render_report` keep working unchanged on a SOC 2-only bundle because bare codes normalize to `soc2:`.

- [ ] **Step 1: Add the AI test fixture bundle.** It is small on purpose: one SOC 2 control, two ISO controls, two AI Act articles (one high-risk only), three guardrails, a scanner, a crosswalk, and a component.

`tests/fixtures/ai_bundle/index.md`:

```markdown
---
okf_version: "0.2"
---
# AI governance fixture bundle
```

`tests/fixtures/ai_bundle/controls/cc6.1.md`:

```markdown
---
type: SOC 2 Control
framework: soc2
title: CC6.1 — Logical Access
tags: [soc2, cc6.1]
---
# Intent
Fixture.
```

`tests/fixtures/ai_bundle/controls/iso42001/a.6.md`:

```markdown
---
type: ISO/IEC 42001 Control
framework: iso42001
title: A.6 — AI system life cycle
tags: [iso42001, iso42001:a.6]
---
# Intent
Fixture.
```

`tests/fixtures/ai_bundle/controls/iso42001/a.7.md`:

```markdown
---
type: ISO/IEC 42001 Control
framework: iso42001
title: A.7 — Data for AI systems
tags: [iso42001, iso42001:a.7]
---
# Intent
Fixture.
```

`tests/fixtures/ai_bundle/controls/eu-ai-act/art-12.md`:

```markdown
---
type: EU AI Act Article
framework: eu-ai-act
title: Art. 12 — Record-keeping
tags: [eu-ai-act, eu-ai-act:art-12]
applies_when:
  risk_tier: [high]
---
# Intent
Fixture.
```

`tests/fixtures/ai_bundle/controls/eu-ai-act/art-50.md`:

```markdown
---
type: EU AI Act Article
framework: eu-ai-act
title: Art. 50 — Transparency
tags: [eu-ai-act, eu-ai-act:art-50]
---
# Intent
Fixture.
```

`tests/fixtures/ai_bundle/policies/llm-prompt-logged.md`:

```markdown
---
type: Semgrep Rule
title: Do not log prompts
tags: [semgrep, iso42001:a.7, eu-ai-act:art-12]
rule_ids: ["semgrep:llm-prompt-logged"]
---
# Remediation
Log a prompt hash, not the prompt.
```

`tests/fixtures/ai_bundle/policies/llm-hardcoded-key.md`:

```markdown
---
type: Semgrep Rule
title: No hard-coded LLM API keys
tags: [semgrep, cc6.1, iso42001:a.6]
rule_ids: ["semgrep:llm-hardcoded-key"]
---
# Remediation
Read the key from the environment.
```

`tests/fixtures/ai_bundle/policies/llm-no-ai-disclosure.md`:

```markdown
---
type: Semgrep Rule
title: Disclose AI-generated output
tags: [semgrep, eu-ai-act:art-50]
rule_ids: ["semgrep:llm-no-ai-disclosure"]
---
# Remediation
Add an `ai_generated` field to the response.
```

`tests/fixtures/ai_bundle/scanners/semgrep.md`:

```markdown
---
type: Scanner
title: Semgrep
tags: [sast]
---
# Covers
Fixture.
```

`tests/fixtures/ai_bundle/crosswalk/iso42001-ai-act.md`:

```markdown
---
type: Crosswalk
title: ISO/IEC 42001 ↔ EU AI Act
tags: [crosswalk]
---
# Links

- [A.7](../controls/iso42001/a.7.md) ↔ [Art. 12](../controls/eu-ai-act/art-12.md)
- [A.6](../controls/iso42001/a.6.md) only, no pair on this line
```

`tests/fixtures/ai_bundle/stack/assistant.md`:

```markdown
---
type: Stack Component
title: Assistant
description: Fixture AI feature.
tags: [ai]
---
- [CC6.1](../controls/cc6.1.md)
- [A.6](../controls/iso42001/a.6.md)
- [A.7](../controls/iso42001/a.7.md)
- [Art. 50](../controls/eu-ai-act/art-50.md)
```

`tests/fixtures/ai_findings.json` (used from Task 2 on; `llm-unbounded-call` is undeclared in this fixture, so it is a gap here):

```json
[
  {"tool": "semgrep", "rule_id": "llm-prompt-logged", "severity": "high", "target": "app/assistant/views.py", "message": "prompt written to log", "tags": []},
  {"tool": "semgrep", "rule_id": "llm-hardcoded-key", "severity": "high", "target": "app/assistant/settings.py", "message": "hard-coded API key", "tags": []},
  {"tool": "semgrep", "rule_id": "llm-unbounded-call", "severity": "medium", "target": "app/assistant/views.py", "message": "no timeout", "tags": []}
]
```

- [ ] **Step 2: Write the failing tests.**

`tests/test_multi_framework.py`:

```python
"""Controls from several frameworks, keyed `framework:code`, under the same grounding rule."""

from pathlib import Path

import pytest

from okf_lib import BundleError, control_key, load_bundle

FIXTURES = Path(__file__).parent / "fixtures"
AI = load_bundle(FIXTURES / "ai_bundle")


def _write(root: Path, rel: str, frontmatter: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n", encoding="utf-8")


def test_control_keys_are_framework_qualified() -> None:
    assert [c.key for c in AI.controls()] == [
        "soc2:cc6.1", "eu-ai-act:art-12", "eu-ai-act:art-50", "iso42001:a.6", "iso42001:a.7",
    ]


def test_framework_defaults_to_soc2() -> None:
    bundle = load_bundle(FIXTURES / "bundle")
    assert {c.framework for c in bundle.controls()} == {"soc2"}


def test_control_key_normalizes_bare_soc2_tags() -> None:
    assert control_key("cc6.1") == "soc2:cc6.1"
    assert control_key("iso42001:a.6") == "iso42001:a.6"


def test_lookup_by_key_and_bare_soc2_code() -> None:
    assert AI.control("iso42001:a.6").title.startswith("A.6")
    assert AI.control("cc6.1") is AI.control("soc2:cc6.1")
    assert AI.control("a.6") is None


def test_one_guardrail_can_declare_one_control_per_framework() -> None:
    key = AI.concepts["policies/llm-hardcoded-key"]
    assert key.control_keys == ("soc2:cc6.1", "iso42001:a.6")
    assert [c.id for c in AI.declaring("iso42001:a.6")] == ["policies/llm-hardcoded-key"]


@pytest.mark.parametrize(
    "tags", ["[iso42001:a.6, iso42001:a.7]", "[cc6.1, cc7.1, iso42001:a.6]", "[iso42001]"]
)
def test_two_controls_in_one_framework_are_rejected(tmp_path: Path, tags: str) -> None:
    _write(tmp_path, "p/bad.md", f'type: Semgrep Rule\ntags: {tags}\nrule_ids: ["semgrep:x"]')
    with pytest.raises(BundleError, match="p/bad.md"):
        load_bundle(tmp_path)


@pytest.mark.parametrize(
    "frontmatter",
    [
        "type: ISO/IEC 42001 Control\nframework: eu-ai-act",
        "type: SOC 2 Control\nframework: iso42001",
        "type: EU AI Act Article\nframework: nist-ai-rmf",
        "type: EU AI Act Article\nframework: eu-ai-act\napplies_when: {risk_tier: high}",
        "type: EU AI Act Article\nframework: eu-ai-act\napplies_when: [high]",
    ],
)
def test_malformed_control_frontmatter_is_rejected(tmp_path: Path, frontmatter: str) -> None:
    _write(tmp_path, "controls/x.md", frontmatter)
    with pytest.raises(BundleError, match="controls/x.md"):
        load_bundle(tmp_path)


def test_crosswalk_pairs_are_lines_linking_two_controls() -> None:
    assert AI.crosswalk_pairs() == [
        ("crosswalk/iso42001-ai-act", "controls/iso42001/a.7", "controls/eu-ai-act/art-12"),
    ]
```

`tests/test_applicability.py`:

```python
"""`applies_when` + the AI inventory decide which controls are in scope; `not-applicable` is never a pass."""

from pathlib import Path

import pytest

from okf_lib import applies, load_bundle

FIXTURES = Path(__file__).parent / "fixtures"
AI = load_bundle(FIXTURES / "ai_bundle")


@pytest.mark.parametrize(
    ("context", "expected"),
    [({"risk_tier": "limited"}, False), ({"risk_tier": "high"}, True), ({}, True)],
)
def test_applies_reads_the_risk_tier(context: dict, expected: bool) -> None:
    assert applies(AI.control("eu-ai-act:art-12"), context) is expected


def test_control_without_applies_when_always_applies() -> None:
    assert applies(AI.control("eu-ai-act:art-50"), {"risk_tier": "minimal"})
```

- [ ] **Step 3: Run them to confirm they fail.**

Run: `uv run pytest tests/test_multi_framework.py tests/test_applicability.py -q`
Expected: collection error, `ImportError: cannot import name 'control_key' from 'okf_lib'` (and `applies`).

- [ ] **Step 4: Replace `okf_lib.py`.** Changes versus v1: the framework constants; `_CONTROL_TAG` also matches `iso42001:a.N` and `eu-ai-act:art-N`; `control_key`, `applies`; `Concept.control_keys/framework/key`; `controls()` covers every framework type; `control()`/`declaring()` take keys; `crosswalk_pairs()`; `_check_grounding` enforces one control tag **per framework**; `_check_control` rejects a `framework` that does not match the type and an `applies_when` that is not a map of lists.

`.claude/skills/grc-continuous-compliance/scripts/okf_lib.py`:

```python
"""Load an OKF v0.2 bundle into an in-memory concept graph."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import yaml

RESERVED = frozenset({"index.md", "log.md"})
CONTROL_TYPE = "SOC 2 Control"
FRAMEWORK_TYPES = {"soc2": CONTROL_TYPE, "iso42001": "ISO/IEC 42001 Control", "eu-ai-act": "EU AI Act Article"}
FRAMEWORK_TITLES = {"soc2": "SOC 2", "iso42001": "ISO/IEC 42001", "eu-ai-act": "EU AI Act"}
DEFAULT_FRAMEWORK = "soc2"
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
    return Bundle(concepts=concepts)
```

- [ ] **Step 5: Name the framework on the five SOC 2 controls.** In each of `knowledge/controls/cc6.1.md`, `cc6.6.md`, `cc7.1.md`, `cc7.2.md`, `cc8.1.md`, add one line directly under `type: SOC 2 Control`:

```yaml
framework: soc2
```

- [ ] **Step 6: Update the conformance test for per-framework grounding.** Apply this change to `tests/test_bundle_conformance.py`:

```diff
diff --git a/tests/test_bundle_conformance.py b/tests/test_bundle_conformance.py
index c408efe..ed1eb65 100644
--- a/tests/test_bundle_conformance.py
+++ b/tests/test_bundle_conformance.py
@@ -6,11 +6,11 @@ from pathlib import Path
 import pytest
 import yaml
 
-from okf_lib import load_bundle
+from okf_lib import FRAMEWORK_TYPES, load_bundle
 
 KNOWLEDGE = Path(__file__).parent.parent / "knowledge"
 TOOLS = {"semgrep", "trivy", "checkov", "conftest"}
-TYPES = {"SOC 2 Control", "Stack Component", "Rego Policy", "Semgrep Rule", "Scanner", "Reference"}
+TYPES = {*FRAMEWORK_TYPES.values(), "Crosswalk", "Stack Component", "Rego Policy", "Semgrep Rule", "Scanner", "Reference"}
 BUNDLE = load_bundle(KNOWLEDGE)  # raises BundleError on a missing or empty `type` (OKF §11)
 
 
@@ -35,7 +35,8 @@ def test_rule_declarations_are_grounded(concept) -> None:
         tool, _, rule = entry.partition(":")
         assert tool in TOOLS, f"{concept.path}: unknown tool in {entry!r}"
         assert re.fullmatch(r"[^*?\[\]]+\*?", rule), f"{concept.path}: {entry!r} is not a literal prefix"
-    assert len(concept.control_tags) == 1, f"{concept.path}: rule_ids need exactly one control tag"
+    frameworks = [key.partition(":")[0] for key in concept.control_keys]
+    assert frameworks and len(frameworks) == len(set(frameworks)), f"{concept.path}: one control tag per framework"
 
 
 def test_every_control_tag_names_a_control() -> None:
@@ -44,9 +45,14 @@ def test_every_control_tag_names_a_control() -> None:
             assert BUNDLE.control(tag), f"{concept.path}: tag {tag} has no control concept"
 
 
-def test_controls_carry_their_own_code_as_tag() -> None:
+def test_every_control_names_its_framework() -> None:
     for control in BUNDLE.controls():
-        assert control.code in control.tags, control.path
+        assert control.frontmatter.get("framework") in FRAMEWORK_TYPES, control.path
+
+
+def test_controls_carry_their_own_key_as_tag() -> None:
+    for control in BUNDLE.controls():
+        assert control.key in control.control_keys, control.path
 
 
 def test_no_broken_links() -> None:
```

- [ ] **Step 7: Run the whole suite.**

Run: `uv run pytest -q`
Expected: `154 passed, 9 deselected`. The v1 tests pass unchanged: bare SOC 2 codes still resolve.

- [ ] **Step 8: Commit.**

```bash
git add .claude/skills/grc-continuous-compliance/scripts/okf_lib.py knowledge/controls tests
git commit -m "Add frameworks, control keys, applicability, and crosswalks to okf_lib" -m "Closes #<A1>"
```

---

## Task 2: Framework keys and applicability across map, OSCAL, and report

**Files:**
- Modify (full replacements below): `.claude/skills/grc-continuous-compliance/scripts/map_findings.py`, `to_oscal.py`, `render_report.py`
- Modify: `app/SEEDED.yaml`, `tests/test_seeded_ledger.py`, `tests/test_integration.py`, `tests/test_map_findings.py`, `tests/test_to_oscal.py`, `tests/test_render_report.py`, `tests/fixtures/report.golden.md`, `docs/oscal-subset.md`
- Test: `tests/test_applicability.py`, `tests/test_multi_framework.py` (extend)

**Interfaces:**
- Produces: `mapping.json` keyed by `framework:code`; new status `not-applicable` with `"reason": "control-not-applicable"` on that entry only (other entries keep the v1 shape exactly); `map_findings(bundle, findings, context=None)`; `load_context(inventory_path) -> {"risk_tier": ...}` (empty when the file is missing, which means "assess everything"); `map_findings.py --inventory` (default `app/ai-inventory.yaml`).
- OSCAL: one back-matter resource and one `control-implementation` per framework (ISO 42001 is a declared placeholder; the AI Act links EUR-Lex); `reviewed-controls` has one `control-selection` per framework; `not-applicable` controls are neither reviewed nor findings and are listed in `remarks`.
- Report: summary rows in framework order with natural code order (`art-9` before `art-10`); one `## <framework>` section per framework present; `## Crosswalk` when the bundle has crosswalks; `## Not applicable` when any control is, with its findings still listed.
- Consumes: Task 1's `okf_lib`.

- [ ] **Step 1: Write the failing tests.**

Replace `tests/test_applicability.py` with the full version (Task 1's tests plus the mapping tests):

```python
"""`applies_when` + the AI inventory decide which controls are in scope; `not-applicable` is never a pass."""

import json
from pathlib import Path

import pytest

from map_findings import load_context, map_findings
from okf_lib import applies, load_bundle

FIXTURES = Path(__file__).parent / "fixtures"
AI = load_bundle(FIXTURES / "ai_bundle")
FINDINGS = json.loads((FIXTURES / "ai_findings.json").read_text())


@pytest.mark.parametrize(
    ("context", "expected"),
    [({"risk_tier": "limited"}, False), ({"risk_tier": "high"}, True), ({}, True)],
)
def test_applies_reads_the_risk_tier(context: dict, expected: bool) -> None:
    assert applies(AI.control("eu-ai-act:art-12"), context) is expected


def test_control_without_applies_when_always_applies() -> None:
    assert applies(AI.control("eu-ai-act:art-50"), {"risk_tier": "minimal"})


def test_limited_tier_marks_high_risk_article_not_applicable() -> None:
    entry = map_findings(AI, FINDINGS, {"risk_tier": "limited"})["controls"]["eu-ai-act:art-12"]
    assert entry["status"] == "not-applicable"
    assert entry["reason"] == "control-not-applicable"
    assert [f["rule_id"] for f in entry["findings"]] == ["llm-prompt-logged"]


def test_same_finding_still_counts_on_an_applicable_control() -> None:
    controls = map_findings(AI, FINDINGS, {"risk_tier": "limited"})["controls"]
    assert controls["iso42001:a.7"]["status"] == "not-satisfied"


def test_high_tier_assesses_the_article() -> None:
    entry = map_findings(AI, FINDINGS, {"risk_tier": "high"})["controls"]["eu-ai-act:art-12"]
    assert entry["status"] == "not-satisfied"
    assert "reason" not in entry


def test_no_inventory_means_assess_everything() -> None:
    statuses = {e["status"] for e in map_findings(AI, FINDINGS)["controls"].values()}
    assert "not-applicable" not in statuses


def test_not_applicable_is_never_a_gap_or_a_clean_result() -> None:
    mapping = map_findings(AI, [], {"risk_tier": "limited"})
    assert mapping["controls"]["eu-ai-act:art-12"]["status"] == "not-applicable"
    assert mapping["unmapped"] == []


def test_load_context(tmp_path: Path) -> None:
    inventory = tmp_path / "ai-inventory.yaml"
    assert load_context(inventory) == {}
    inventory.write_text("risk_tier: limited\nsystems: []\n", encoding="utf-8")
    assert load_context(inventory) == {"risk_tier": "limited"}
```

Append to `tests/test_multi_framework.py` (and add `import json` and `from map_findings import map_findings` to its imports):

```python


def test_a_finding_maps_to_each_declared_framework() -> None:
    findings = json.loads((FIXTURES / "ai_findings.json").read_text())
    controls = map_findings(AI, findings)["controls"]
    for key in ("soc2:cc6.1", "iso42001:a.6"):
        assert [f["rule_id"] for f in controls[key]["findings"]] == ["llm-hardcoded-key"]
```

Append to `tests/test_to_oscal.py`:

```python
AI_BUNDLE = FIXTURES / "ai_bundle"


def _ai() -> tuple[Bundle, dict]:
    ai = load_bundle(AI_BUNDLE)
    findings = json.loads((FIXTURES / "ai_findings.json").read_text())
    return ai, map_findings(ai, findings, {"risk_tier": "limited"})


def test_one_control_implementation_per_framework_source() -> None:
    ai, _ = _ai()
    doc = component_definition(ai, NOW)
    validate(doc, "oscal_component_schema.json")
    (comp,) = doc["component-definition"]["components"]
    resources = {f"#{r['uuid']}": r["title"] for r in doc["component-definition"]["back-matter"]["resources"]}
    by_source = {
        resources[ci["source"]].split(" ")[0]: [r["control-id"] for r in ci["implemented-requirements"]]
        for ci in comp["control-implementations"]
    }
    assert by_source == {"AICPA": ["cc6.1"], "ISO/IEC": ["a.6", "a.7"], "Regulation": ["art-50"]}


def test_iso42001_source_is_a_declared_placeholder() -> None:
    ai, _ = _ai()
    resources = component_definition(ai, NOW)["component-definition"]["back-matter"]["resources"]
    (iso,) = [r for r in resources if r["title"].startswith("ISO/IEC 42001")]
    assert "placeholder" in iso["title"] and "rlinks" not in iso
    (act,) = [r for r in resources if r["title"].startswith("Regulation (EU) 2024/1689")]
    assert act["rlinks"] == [{"href": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj"}]


def test_not_applicable_controls_are_neither_reviewed_nor_findings() -> None:
    ai, mapping = _ai()
    doc = assessment_results(ai, mapping, NOW)
    validate(doc, "oscal_assessment-results_schema.json")
    (result,) = doc["assessment-results"]["results"]
    reviewed = [
        c["control-id"] for s in result["reviewed-controls"]["control-selections"] for c in s["include-controls"]
    ]
    assert "art-12" not in reviewed
    assert "art-12" not in {f["target"]["target-id"] for f in result["findings"]}
    assert "Not applicable at the declared AI risk tier: eu-ai-act:art-12" in result["remarks"]


def test_reviewed_controls_are_grouped_by_framework() -> None:
    ai, mapping = _ai()
    (result,) = assessment_results(ai, mapping, NOW)["assessment-results"]["results"]
    selections = result["reviewed-controls"]["control-selections"]
    assert [s["description"].split(" ")[0] for s in selections] == ["AICPA", "ISO/IEC", "Regulation"]
```

Append to `tests/test_render_report.py`:

```python
def _ai_report() -> str:
    bundle = load_bundle(FIXTURES / "ai_bundle")
    findings = json.loads((FIXTURES / "ai_findings.json").read_text())
    mapping = map_findings(bundle, findings, {"risk_tier": "limited"})
    return render_report(bundle, mapping, "2026-09-25T12:00:00+00:00")


def test_one_section_per_framework_in_order() -> None:
    headings = [ln for ln in _ai_report().splitlines() if ln.startswith("## ")]
    assert headings == [
        "## Risk posture", "## Summary", "## SOC 2", "## ISO/IEC 42001", "## EU AI Act",
        "## Crosswalk", "## Coverage gaps", "## Not assessed", "## Not applicable",
    ]


def test_crosswalk_row_shows_each_side_status() -> None:
    assert (
        "| iso42001:a.7 | not-satisfied | eu-ai-act:art-12 | not-applicable | "
        "[ISO/IEC 42001 ↔ EU AI Act](../knowledge/crosswalk/iso42001-ai-act.md) |"
    ) in _ai_report()


def test_not_applicable_is_counted_apart_and_keeps_its_findings() -> None:
    report = _ai_report()
    assert "3 open findings across 3 of 4 controls: 3 high." in report
    summary = report.split("## Summary", 1)[1].split("## SOC 2", 1)[0]
    assert [ln.split(" | ")[0] for ln in summary.splitlines() if ln.startswith("| ") and ":" in ln] == [
        "| soc2:cc6.1", "| iso42001:a.6", "| iso42001:a.7", "| eu-ai-act:art-12", "| eu-ai-act:art-50",
    ]
    assert "1 control shows no violations. 0 not assessed. 1 not applicable. 1 coverage gap to triage." in report
    na = report.split("## Not applicable", 1)[1]
    assert "- Art. 12 — Record-keeping" in na and "`llm-prompt-logged`" in na
```

Move the v1 test expectations to framework keys. In `tests/test_map_findings.py`, every SOC 2 key gains the `soc2:` prefix; in `tests/test_to_oscal.py`, the two `remarks` assertions do too:

```diff
diff --git a/tests/test_map_findings.py b/tests/test_map_findings.py
index ed5f140..3d3d2fd 100644
--- a/tests/test_map_findings.py
+++ b/tests/test_map_findings.py
@@ -22,15 +22,15 @@ def _rules(findings: list[dict]) -> list[str]:
 
 
 def test_every_bundle_control_is_reported(mapping: dict) -> None:
-    assert sorted(mapping["controls"]) == ["cc6.1", "cc7.1", "cc7.2", "cc8.1"]
+    assert sorted(mapping["controls"]) == ["soc2:cc6.1", "soc2:cc7.1", "soc2:cc7.2", "soc2:cc8.1"]
 
 
 def test_declared_rules_map_to_their_control(mapping: dict) -> None:
-    assert _rules(mapping["controls"]["cc6.1"]["findings"]) == ["require_non_root", "CKV_TEST_1"]
+    assert _rules(mapping["controls"]["soc2:cc6.1"]["findings"]) == ["require_non_root", "CKV_TEST_1"]
 
 
 def test_glob_rule_maps_cve(mapping: dict) -> None:
-    assert _rules(mapping["controls"]["cc7.1"]["findings"]) == ["CVE-2024-0001"]
+    assert _rules(mapping["controls"]["soc2:cc7.1"]["findings"]) == ["CVE-2024-0001"]
 
 
 def test_undeclared_rule_is_a_gap_not_a_mapping(mapping: dict) -> None:
@@ -42,22 +42,22 @@ def test_undeclared_rule_is_a_gap_not_a_mapping(mapping: dict) -> None:
 def test_control_missing_from_bundle_is_a_gap(mapping: dict) -> None:
     gaps = {g["finding"]["rule_id"]: g["reason"] for g in mapping["unmapped"]}
     assert gaps["orphan_rule"] == "control-not-in-bundle"
-    assert "cc9.9" not in mapping["controls"]
+    assert "soc2:cc9.9" not in mapping["controls"]
 
 
 def test_statuses(mapping: dict) -> None:
     status = {code: c["status"] for code, c in mapping["controls"].items()}
     assert status == {
-        "cc6.1": "not-satisfied",
-        "cc7.1": "not-satisfied",
-        "cc7.2": "not-assessed",
-        "cc8.1": "no-violations-detected",
+        "soc2:cc6.1": "not-satisfied",
+        "soc2:cc7.1": "not-satisfied",
+        "soc2:cc7.2": "not-assessed",
+        "soc2:cc8.1": "no-violations-detected",
     }
 
 
 def test_evidence_links(mapping: dict) -> None:
-    assert mapping["controls"]["cc7.1"]["evidenced_by"] == ["scanners/trivy"]
-    assert mapping["controls"]["cc8.1"]["satisfied_by"] == ["policies/deny-latest-tag"]
+    assert mapping["controls"]["soc2:cc7.1"]["evidenced_by"] == ["scanners/trivy"]
+    assert mapping["controls"]["soc2:cc8.1"]["satisfied_by"] == ["policies/deny-latest-tag"]
 
 
 def _write(root: Path, rel: str, frontmatter: str) -> None:
@@ -73,9 +73,9 @@ def test_evidence_comes_from_declarations_not_hand_tags(tmp_path: Path) -> None:
     _write(tmp_path, "scanners/semgrep.md", "type: Scanner\ntags: [sast]")
     _write(tmp_path, "policies/p.md", 'type: Rego Policy\ntags: [cc6.1]\nrule_ids: ["checkov:CKV_1"]')
     controls = map_findings(load_bundle(tmp_path), [])["controls"]
-    assert controls["cc7.2"] == {
+    assert controls["soc2:cc7.2"] == {
         "status": "not-assessed", "findings": [], "evidenced_by": [], "satisfied_by": []
     }
-    assert controls["cc6.1"]["evidenced_by"] == ["scanners/checkov"]
-    assert controls["cc6.1"]["satisfied_by"] == ["policies/p"]
-    assert controls["cc6.1"]["status"] == "no-violations-detected"
+    assert controls["soc2:cc6.1"]["evidenced_by"] == ["scanners/checkov"]
+    assert controls["soc2:cc6.1"]["satisfied_by"] == ["policies/p"]
+    assert controls["soc2:cc6.1"]["status"] == "no-violations-detected"
diff --git a/tests/test_to_oscal.py b/tests/test_to_oscal.py
index 976e514..5c355f9 100644
--- a/tests/test_to_oscal.py
+++ b/tests/test_to_oscal.py
@@ -45,7 +45,7 @@ def test_findings_only_for_violated_controls(bundle: Bundle, mapping: dict) -> N
 def test_clean_controls_are_never_attested(bundle: Bundle, mapping: dict) -> None:
     (result,) = assessment_results(bundle, mapping, NOW)["assessment-results"]["results"]
     assert "satisfied" not in {f["target"]["status"]["state"] for f in result["findings"]}
-    assert "not a control attestation): cc8.1" in result["remarks"]
-    assert "Not assessed (no in-bundle scanner or policy): cc7.2" in result["remarks"]
+    assert "not a control attestation): soc2:cc8.1" in result["remarks"]
+    assert "Not assessed (no in-bundle scanner or policy): soc2:cc7.2" in result["remarks"]
     reviewed = result["reviewed-controls"]["control-selections"][0]["include-controls"]
     assert [c["control-id"] for c in reviewed] == ["cc6.1", "cc7.1", "cc8.1"]
```

- [ ] **Step 2: Run them to confirm they fail.**

Run: `uv run pytest -q`
Expected: failures in `test_applicability.py` (`ImportError: cannot import name 'load_context'`) and in the updated map, OSCAL, and report tests (`KeyError: 'soc2:cc6.1'`, missing `control-selections` grouping, missing `## SOC 2`).

- [ ] **Step 3: Replace `map_findings.py`.**

```python
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
```

- [ ] **Step 4: Replace `to_oscal.py`.**

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
    all_findings = [f for c in mapping["controls"].values() for f in c["findings"]]
    all_findings += [u["finding"] for u in mapping["unmapped"]]
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
    if remarks := _remarks(mapping):
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

- [ ] **Step 5: Replace `render_report.py`.**

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
    return f"- `{f['tool']}` `{f['rule_id']}` ({f['severity']}) — {f['message']} — `{f['target']}`"


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


def _control_section(bundle: Bundle, key: str, entry: Json) -> list[str]:
    evidence = [_link(bundle, cid) for cid in entry["evidenced_by"] + entry["satisfied_by"]]
    lines = [f"### {_title(bundle, key)}", "", f"**Status:** {entry['status']}", ""]
    if entry["findings"]:
        lines += [f"**Findings:** {_breakdown(_counts(entry['findings']))}", ""]
    lines += [f"**Evidence:** {', '.join(evidence) if evidence else 'none in bundle'}", ""]
    if entry["findings"]:
        lines += ["**Open findings:**", "", *map(_finding_line, entry["findings"]), ""]
        if remediation := _remediation(bundle, key, entry["findings"]):
            lines += [f"**Remediation:** {remediation}", ""]
    return lines


def _risk_posture(controls: list[tuple[str, Json]], unmapped: list[Json]) -> list[str]:
    """A one-glance summary: open findings by severity, control status counts, and coverage gaps."""
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
            not_satisfied += 1
        else:
            clean += 1
        for f in entry["findings"]:
            total[_bucket(f["severity"])] += 1
            open_findings += 1
    findings_word = "finding" if open_findings == 1 else "findings"
    clean_clause = "control shows" if clean == 1 else "controls show"
    gaps_word = "coverage gap" if len(unmapped) == 1 else "coverage gaps"
    applicable = len(controls) - not_applicable
    controls_word = "control" if applicable == 1 else "controls"
    na_clause = f" {not_applicable} not applicable." if not_applicable else ""
    return [
        "## Risk posture",
        "",
        f"{open_findings} open {findings_word} across {not_satisfied} of {applicable} {controls_word}: "
        f"{_breakdown(total)}.",
        f"{clean} {clean_clause} no violations. {not_assessed} not assessed.{na_clause} "
        f"{len(unmapped)} {gaps_word} to triage.",
        "",
    ]


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


def render_report(bundle: Bundle, mapping: Json, now: str) -> str:
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
        *_risk_posture(controls, mapping["unmapped"]),
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
                lines += _control_section(bundle, key, entry)
    lines += _crosswalk(bundle, mapping)
    lines += ["## Coverage gaps", ""]
    if mapping["unmapped"]:
        lines += ["Findings with no in-bundle control. These are gaps to close, not mappings to invent.", ""]
        lines += [f"{_finding_line(u['finding'])} — reason: `{u['reason']}`" for u in mapping["unmapped"]]
    else:
        lines.append("None.")
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
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--now", default=datetime.now(UTC).isoformat(timespec="seconds"))
    args = parser.parse_args()
    mapping = json.loads((args.out / "mapping.json").read_text(encoding="utf-8"))
    report = render_report(load_bundle(args.knowledge), mapping, args.now)
    (args.out / "report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Regenerate the golden report and review the diff.**

Run:

```bash
uv run python - <<'EOF'
import json, sys
from pathlib import Path
sys.path.insert(0, ".claude/skills/grc-continuous-compliance/scripts")
from map_findings import map_findings
from okf_lib import load_bundle
from render_report import render_report
fx = Path("tests/fixtures")
bundle = load_bundle(fx / "bundle")
mapping = map_findings(bundle, json.loads((fx / "findings.json").read_text()))
(fx / "report.golden.md").write_text(render_report(bundle, mapping, "2026-09-25T12:00:00+00:00"))
EOF
git diff tests/fixtures/report.golden.md
```

Expected diff: only the four summary rows gain `soc2:` and `## Controls` becomes `## SOC 2`. Any other change is a regression; stop and fix it.

- [ ] **Step 7: Move the seeded ledger to `controls:` lists of keys.** A seed may now land on several controls (AI-2 lands on one SOC 2 and one ISO control), so `expect.control` becomes `expect.controls`.

```diff
diff --git a/app/SEEDED.yaml b/app/SEEDED.yaml
index 5d05d11..a7cf9e2 100644
--- a/app/SEEDED.yaml
+++ b/app/SEEDED.yaml
@@ -1,11 +1,12 @@
 # INTENTIONALLY VULNERABLE SCAN TARGET — DO NOT DEPLOY.
-# Each seeded issue, the scanner rules observed to detect it, and the expected outcome.
+# Each seeded issue, the scanner rules observed to detect it, and the expected outcome:
+# `controls` lists every control key the finding must land on; `gap` names the coverage-gap reason.
 # Asserted by tests/test_integration.py (make test-integration).
 - id: S1
   file: app/Dockerfile
   issue: image runs as root (no USER instruction)
   detected_by: ["trivy:DS-0002", "checkov:CKV_DOCKER_3"]
-  expect: {control: cc6.1}
+  expect: {controls: [soc2:cc6.1]}
 - id: S2
   file: app/Dockerfile
   issue: no HEALTHCHECK (availability, SOC 2 A1 — not in the bundle)
@@ -15,24 +16,24 @@
   file: app/k8s/deployment.yaml
   issue: image uses the :latest tag
   detected_by: ["conftest:deny_latest_tag", "checkov:CKV_K8S_14", "trivy:KSV-0013"]
-  expect: {control: cc8.1}
+  expect: {controls: [soc2:cc8.1]}
 - id: S4
   file: app/k8s/deployment.yaml
   issue: container runs as root (runAsUser 0, runAsNonRoot false)
   detected_by: ["conftest:require_non_root", "checkov:CKV_K8S_23", "trivy:KSV-0012", "trivy:KSV-0105"]
-  expect: {control: cc6.1}
+  expect: {controls: [soc2:cc6.1]}
 - id: S5
   file: app/infra/main.tf
   issue: bucket readable by allUsers
   detected_by: ["conftest:no_public_bucket", "checkov:CKV_GCP_28", "trivy:GCP-0001"]
-  expect: {control: cc6.6}
+  expect: {controls: [soc2:cc6.6]}
 - id: S6
   file: app/widgets/views.py
   issue: DRF viewset uses AllowAny
   detected_by: ["semgrep:drf-allowany"]
-  expect: {control: cc6.1}
+  expect: {controls: [soc2:cc6.1]}
 - id: S7
   file: app/requirements.txt
   issue: Django 4.2.0 has known CVEs
   detected_by: ["trivy:CVE-2023-31047"]
-  expect: {control: cc7.1}
+  expect: {controls: [soc2:cc7.1]}
diff --git a/tests/test_integration.py b/tests/test_integration.py
index 15bbb2a..7fcfbfd 100644
--- a/tests/test_integration.py
+++ b/tests/test_integration.py
@@ -41,10 +41,10 @@ SEEDED = yaml.safe_load((ROOT / "app" / "SEEDED.yaml").read_text())
 
 @pytest.mark.parametrize("seed", SEEDED, ids=lambda s: s["id"])
 def test_seeded_issue_lands_where_expected(mapping: dict, seed: dict) -> None:
-    expected = seed["expect"].get("control") or f"gap:{seed['expect']['gap']}"
+    expected = set(seed["expect"].get("controls", [])) or {f"gap:{seed['expect']['gap']}"}
     for detector in seed["detected_by"]:
         tool, rule_id = detector.split(":", 1)
-        assert _located(mapping, tool, rule_id, seed["file"]) == {expected}, f"{seed['id']} {detector}"
+        assert _located(mapping, tool, rule_id, seed["file"]) == expected, f"{seed['id']} {detector}"
 
 
 def test_outputs_exist_and_oscal_validates(mapping: dict) -> None:
@@ -54,4 +54,4 @@ def test_outputs_exist_and_oscal_validates(mapping: dict) -> None:
 
 
 def test_monitoring_control_is_not_assessed(mapping: dict) -> None:
-    assert mapping["controls"]["cc7.2"]["status"] == "not-assessed"
+    assert mapping["controls"]["soc2:cc7.2"]["status"] == "not-assessed"
```

In `tests/test_seeded_ledger.py`, replace the last line of `test_entry_is_well_formed`:

```python
    assert len(seed["expect"]) == 1 and set(seed["expect"]) <= {"controls", "gap"}
    for key in seed["expect"].get("controls", []):
        assert ":" in key, f"{seed['id']}: control {key!r} is not a framework:code key"
```

- [ ] **Step 8: Document the OSCAL changes.** In `docs/oscal-subset.md`:
  - Retitle to `# OSCAL subset emitted`.
  - In the component-definition table, replace the two `control-implementations` rows with:

```markdown
| `control-implementations[]` | one per framework the component's concept links to (SOC 2, ISO/IEC 42001, EU AI Act) |
| `control-implementations[].implemented-requirements[]` | one per linked control that some concept declares rules for; `control-id` is the code within that framework's source (`cc6.1`, `a.6`, `art-50`) |
| `control-implementations[].source` | `#<uuid>` of that framework's back-matter resource: "AICPA Trust Services Criteria (SOC 2)"; "ISO/IEC 42001:2023 Annex A (placeholder …)"; "Regulation (EU) 2024/1689 (EU AI Act)" with an `rlinks` href to EUR-Lex |
```

  - In the assessment-results table, replace the `reviewed-controls` and `remarks` rows with:

```markdown
| `results[0].reviewed-controls` | one `control-selection` per framework, described by the framework's source title; includes every control whose status is not `not-assessed` or `not-applicable` |
| `results[0].remarks` | lists controls with no violations detected, controls not assessed, and controls not applicable at the declared AI risk tier (by `framework:code` key) |
```

  - Under "Deliberately not modeled", add:

```markdown
- An ISO/IEC 42001 catalog: ISO publishes no OSCAL catalog and the text is
  copyrighted, so the source is a clean-room placeholder resource with no link,
  and `control-id` values are the Annex A group ids (`a.6`).
- `not-applicable` as a finding: a control excluded by the declared AI risk tier
  is not assessed, so it is named in `remarks`, never reported as a pass.
```

- [ ] **Step 9: Run the unit suite, then the integration suite.**

Run: `uv run pytest -q`
Expected: `168 passed, 9 deselected`.

Run: `make test-integration`
Expected: `9 passed` (the v1 seeds land on their `soc2:` keys; OSCAL validates).

- [ ] **Step 10: Commit.**

```bash
git add .claude/skills/grc-continuous-compliance/scripts app/SEEDED.yaml docs/oscal-subset.md tests
git commit -m "Key controls by framework and add not-applicable across map, OSCAL, and report" -m "Closes #<A2>"
```

---

## Task 3: Sample AI assistant feature and seeds AI-1..AI-6 (parallelizable)

**Files:**
- Create: `app/assistant/__init__.py` (empty), `app/assistant/settings.py`, `app/assistant/views.py`, `app/ai-inventory.yaml`
- Modify: `app/SEEDED.yaml`, `.claude/skills/grc-continuous-compliance/scripts/run_scan.py`

**Interfaces:**
- Produces: six seeded issues; `app/ai-inventory.yaml` with `risk_tier: limited`, `components`, and an empty `systems` list; Conftest now also reads `app/ai-inventory.yaml`.
- Consumes: the `controls:` ledger format from Task 2 (if Task 2 has not merged yet, write the AI entries as shown anyway; the ledger test accepts them once Task 2 lands).

- [ ] **Step 1: Write the ledger entries first (the failing test).** Append to `app/SEEDED.yaml`:

```yaml
- id: AI-1
  file: app/assistant/views.py
  issue: the prompt (with user input) is written to the log in clear text
  detected_by: ["semgrep:llm-prompt-logged"]
  expect: {controls: [iso42001:a.7, eu-ai-act:art-12]}
- id: AI-2
  file: app/assistant/settings.py
  issue: the LLM API key is hard-coded
  detected_by: ["semgrep:llm-hardcoded-key"]
  expect: {controls: [soc2:cc6.1, iso42001:a.6]}
- id: AI-3
  file: app/assistant/views.py
  issue: an LLM call has no timeout and no max_tokens bound
  detected_by: ["semgrep:llm-unbounded-call"]
  expect: {controls: [iso42001:a.6]}
- id: AI-4
  file: app/assistant/views.py
  issue: the response does not tell the user that AI wrote it
  detected_by: ["semgrep:llm-no-ai-disclosure"]
  expect: {controls: [eu-ai-act:art-50]}
- id: AI-5
  file: app/ai-inventory.yaml
  issue: the assistant component has no AI inventory entry
  detected_by: ["conftest:ai_inventory_complete"]
  expect: {controls: [iso42001:a.4]}
- id: AI-6
  file: app/assistant/views.py
  issue: AI output is written to a record with no human-review flag (no rule declared)
  detected_by: ["semgrep:llm-output-unreviewed-write"]
  expect: {gap: no-rule-match}
```

Run: `uv run pytest tests/test_seeded_ledger.py -q`
Expected: FAIL on `AI-1` … `AI-6`: `assert (ROOT / seed["file"]).is_file()`.

- [ ] **Step 2: Add the feature.** It is never run; it exists to be scanned. Add no dependency to `app/requirements.txt` (a new pin would change the Trivy CVE set for reasons unrelated to this spec).

`app/assistant/__init__.py`: empty file.

`app/assistant/settings.py`:

```python
# INTENTIONALLY VULNERABLE — DO NOT DEPLOY. Settings for the assistant feature.
# AI-2: the API key is hard-coded. The value is a placeholder, not a real key.
ANTHROPIC_API_KEY = "placeholder-not-a-real-key"
ASSISTANT_MODEL = "claude-haiku-4-5"
```

`app/assistant/views.py`:

```python
# INTENTIONALLY VULNERABLE — DO NOT DEPLOY. Never run; it exists to be scanned.
# Seeds AI-1, AI-3, AI-4 and AI-6 (see app/SEEDED.yaml).
import logging

import anthropic
from rest_framework.decorators import api_view
from rest_framework.response import Response

from widgets.models import Widget

from .settings import ANTHROPIC_API_KEY, ASSISTANT_MODEL

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


@api_view(["POST"])
def summarize(request):
    widget = Widget.objects.get(pk=request.data["widget_id"])
    prompt = f"Summarize this widget for a customer:\n{widget.description}\n{request.data.get('note', '')}"
    logger.info("assistant prompt: %s", prompt)
    completion = client.messages.create(
        model=ASSISTANT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return Response({"widget": widget.pk, "summary": completion.content[0].text})


@api_view(["POST"])
def rewrite_description(request):
    widget = Widget.objects.get(pk=request.data["widget_id"])
    completion = client.messages.create(
        model=ASSISTANT_MODEL,
        max_tokens=512,
        timeout=30,
        messages=[{"role": "user", "content": f"Rewrite: {widget.description}"}],
    )
    widget.description = completion.content[0].text
    widget.save()
    return Response({"widget": widget.pk, "ai_generated": True})
```

`app/ai-inventory.yaml`:

```yaml
# INTENTIONALLY INCOMPLETE — seed AI-5: the assistant component has no system entry.
# risk_tier drives `applies_when` in the knowledge bundle (EU AI Act risk classes).
risk_tier: limited
components:
  - {path: app/widgets, kind: api}
  - {path: app/assistant, kind: assistant}
systems: []
```

- [ ] **Step 3: Feed the inventory to Conftest.** In `run_scan.py`, `scan()`, extend the Conftest input globs:

```python
        for pattern in ("k8s/**/*.yaml", "k8s/**/*.yml", "infra/**/*.tf", "ai-inventory.yaml")
```

The existing Rego policies ignore this document: `lib.k8s` only reads workload kinds and `no_public_bucket` only reads `input.resource`. Checkov and Trivy do not treat it as IaC. (Verified in the prototype scan: the only new finding from this file is `conftest:ai_inventory_complete`.)

- [ ] **Step 4: Run the ledger test.**

Run: `uv run pytest tests/test_seeded_ledger.py -q`
Expected: all pass (13 seeds).

- [ ] **Step 5: Commit.**

```bash
git add app .claude/skills/grc-continuous-compliance/scripts/run_scan.py
git commit -m "Add the sample AI assistant feature with seeds AI-1 to AI-6" -m "Closes #<A3>"
```

`make test-integration` fails on the AI seeds until Task 6 lands (no rules, then no declarations yet). That is expected; do not weaken the test.

---

## Task 4: AI governance rules: Semgrep and Rego (parallelizable)

**Files:**
- Create: `policies/semgrep/llm-prompt-logged.{yaml,py}`, `llm-hardcoded-key.{yaml,py}`, `llm-unbounded-call.{yaml,py}`, `llm-no-ai-disclosure.{yaml,py}`, `llm-output-unreviewed-write.{yaml,py}`
- Create: `policies/rego/ai_inventory_complete.rego`, `policies/rego/ai_inventory_complete_test.rego`

**Interfaces:**
- Produces rule ids: `semgrep:llm-prompt-logged`, `semgrep:llm-hardcoded-key`, `semgrep:llm-unbounded-call`, `semgrep:llm-no-ai-disclosure`, `semgrep:llm-output-unreviewed-write` (deliberately undeclared, D4), `conftest:ai_inventory_complete` (D3).

Each rule ships with a Semgrep test file (`# ruleid:` / `# ok:` annotations) or a Rego `_test.rego`, as in v1. Write the test file first, run `make test` to see it fail (Semgrep reports the rule file missing, OPA reports `deny` undefined), then add the rule.

- [ ] **Step 1: `llm-prompt-logged`.** The variable-name regex matches `prompt`, `completion`, and `user_prompt`, but not `prompt_id`.

`policies/semgrep/llm-prompt-logged.py`:

```python
import logging

logger = logging.getLogger(__name__)


def handler(prompt, completion, prompt_id, user_prompt):
    # ruleid: llm-prompt-logged
    logger.error("failed on %s", user_prompt)
    # ruleid: llm-prompt-logged
    logger.info("prompt: %s", prompt)
    # ruleid: llm-prompt-logged
    logger.debug("got %s", completion.content)
    # ruleid: llm-prompt-logged
    logging.warning(prompt)
    # ok: llm-prompt-logged
    logger.info("request %s done", prompt_id.hex)
    # ok: llm-prompt-logged
    logger.info("request done")
```

`policies/semgrep/llm-prompt-logged.yaml`:

```yaml
rules:
  - id: llm-prompt-logged
    languages: [python]
    severity: ERROR
    message: A prompt or model completion is written to the log in clear text; log a hash or an id instead.
    patterns:
      - pattern-either:
          - pattern: $LOG.$LEVEL(..., $VAR, ...)
          - pattern: $LOG.$LEVEL(..., $VAR.$ATTR, ...)
      - metavariable-regex:
          metavariable: $LOG
          regex: ^(logger|log|logging)$
      - metavariable-regex:
          metavariable: $LEVEL
          regex: ^(debug|info|warning|error|critical|exception|log)$
      - metavariable-regex:
          metavariable: $VAR
          regex: (?i)^([a-z0-9]+_)*(prompt|completion)s?$
```

- [ ] **Step 2: `llm-hardcoded-key`.**

`policies/semgrep/llm-hardcoded-key.py`:

```python
import os

# ruleid: llm-hardcoded-key
ANTHROPIC_API_KEY = "placeholder-not-a-real-key"
# ruleid: llm-hardcoded-key
OPENAI_API_KEY = ""
# ok: llm-hardcoded-key
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
# ok: llm-hardcoded-key
API_KEY_HEADER = "x-api-key"
```

`policies/semgrep/llm-hardcoded-key.yaml`:

```yaml
rules:
  - id: llm-hardcoded-key
    languages: [python]
    severity: ERROR
    message: An API key is assigned from a string literal; read it from the environment or a secret store.
    patterns:
      - pattern: $NAME = "..."
      - metavariable-regex:
          metavariable: $NAME
          regex: ^[A-Z0-9_]*_API_KEY$
```

- [ ] **Step 3: `llm-unbounded-call`.** Semgrep matches keyword arguments in any order, so one `pattern-not` covers both orders.

`policies/semgrep/llm-unbounded-call.py`:

```python
def call(client, prompt):
    # ruleid: llm-unbounded-call
    client.messages.create(model="m", messages=prompt)
    # ruleid: llm-unbounded-call
    client.messages.create(model="m", max_tokens=100, messages=prompt)
    # ruleid: llm-unbounded-call
    client.messages.create(model="m", timeout=30, messages=prompt)
    # ok: llm-unbounded-call
    client.messages.create(model="m", max_tokens=100, timeout=30, messages=prompt)
    # ok: llm-unbounded-call
    client.messages.create(timeout=30, model="m", messages=prompt, max_tokens=100)
```

`policies/semgrep/llm-unbounded-call.yaml`:

```yaml
rules:
  - id: llm-unbounded-call
    languages: [python]
    severity: WARNING
    message: LLM call without both a timeout and a max_tokens bound; set both.
    patterns:
      - pattern: $CLIENT.messages.create(...)
      - pattern-not: $CLIENT.messages.create(..., timeout=$T, max_tokens=$M, ...)
```

- [ ] **Step 4: `llm-no-ai-disclosure`.**

`policies/semgrep/llm-no-ai-disclosure.py`:

```python
from rest_framework.response import Response


def summarize(client, request):
    out = client.messages.create(model="m", max_tokens=10, timeout=5, messages=[])
    # ruleid: llm-no-ai-disclosure
    return Response({"summary": out.content[0].text})


def disclosed(client, request):
    out = client.messages.create(model="m", max_tokens=10, timeout=5, messages=[])
    # ok: llm-no-ai-disclosure
    return Response({"summary": out.content[0].text, "ai_generated": True})


def no_model(request):
    # ok: llm-no-ai-disclosure
    return Response({"summary": "static"})
```

`policies/semgrep/llm-no-ai-disclosure.yaml`:

```yaml
rules:
  - id: llm-no-ai-disclosure
    languages: [python]
    severity: WARNING
    message: A view returns model output without telling the user it is AI-generated; add an ai_generated field.
    patterns:
      - pattern-inside: |
          def $VIEW(...):
              ...
              $OUT = $CLIENT.messages.create(...)
              ...
      - pattern: Response({...})
      - pattern-not: 'Response({..., "ai_generated": $V, ...})'
```

- [ ] **Step 5: `llm-output-unreviewed-write` (the AI-6 detector; no concept will declare it).**

`policies/semgrep/llm-output-unreviewed-write.py`:

```python
def apply(widget, out, request):
    # ruleid: llm-output-unreviewed-write
    widget.description = out.content[0].text
    if request.data.get("human_reviewed"):
        # ok: llm-output-unreviewed-write
        widget.description = out.content[0].text
    if human_reviewed(widget):
        # ok: llm-output-unreviewed-write
        widget.name = out.content[0].text
    # ok: llm-output-unreviewed-write
    summary = out.content[0].text
```

`policies/semgrep/llm-output-unreviewed-write.yaml`:

```yaml
rules:
  - id: llm-output-unreviewed-write
    languages: [python]
    severity: WARNING
    message: Model output is written to a record with no human-review flag checked first.
    patterns:
      - pattern: $OBJ.$ATTR = $OUT.content[$I].text
      - pattern-not-inside: |
          if <... human_reviewed ...>:
              ...
      - pattern-not-inside: |
          if <... "human_reviewed" ...>:
              ...
```

- [ ] **Step 6: `ai_inventory_complete` (Rego).**

`policies/rego/ai_inventory_complete_test.rego`:

```rego
package ai_inventory_complete

import rego.v1

inventory(systems) := {"risk_tier": "limited", "components": [{"path": "app/assistant", "kind": "assistant"}, {"path": "app/widgets", "kind": "api"}], "systems": systems}

test_missing_assistant_entry_denied if count(deny) == 1 with input as inventory([])

test_listed_assistant_allowed if count(deny) == 0 with input as inventory([{"path": "app/assistant"}])

test_non_ai_component_ignored if {
	count(deny) == 0 with input as {"components": [{"path": "app/widgets", "kind": "api"}], "systems": []}
}

test_other_documents_ignored if count(deny) == 0 with input as {"kind": "Deployment"}
```

`policies/rego/ai_inventory_complete.rego`:

```rego
package ai_inventory_complete

import rego.v1

deny contains msg if {
	some component in input.components
	component.kind == "assistant"
	not inventoried(component.path)
	msg := sprintf("AI component %q has no entry in the AI system inventory", [component.path])
}

inventoried(path) if {
	some system in input.systems
	system.path == path
}
```

- [ ] **Step 7: Run the rule tests.**

Run: `make test`
Expected: pytest green; `conftest verify` reports 0 failures; Semgrep reports `6/6: ✓ All tests passed`.

If Task 3 has merged, also confirm the detectors fire on the app exactly once each:

```bash
PATH=$PWD/.tools/bin:$PATH semgrep scan --config policies/semgrep --metrics=off --json --quiet app \
  | uv run python -c "import json,sys; [print(r['check_id'].rsplit('.',1)[-1], r['path'], r['start']['line']) for r in json.load(sys.stdin)['results']]"
.tools/bin/conftest test --all-namespaces --no-color -p policies/rego app/ai-inventory.yaml
```

Expected: one line each for `llm-hardcoded-key` (`settings.py`), `llm-prompt-logged`, `llm-unbounded-call`, `llm-no-ai-disclosure`, `llm-output-unreviewed-write` (`views.py`), plus the v1 `drf-allowany`; and one Conftest failure, `AI component "app/assistant" has no entry in the AI system inventory`.

- [ ] **Step 8: Commit.**

```bash
git add policies
git commit -m "Add AI governance Semgrep rules and the AI inventory Rego policy" -m "Closes #<A4>"
```

---

## Task 5: ISO 42001 / EU AI Act concepts and crosswalks (draft; do not commit)

**Files:**
- Create: `knowledge/controls/iso42001/{index,a.4,a.5,a.6,a.7,a.8,a.9}.md`
- Create: `knowledge/controls/eu-ai-act/{index,art-9,art-10,art-12,art-13,art-14,art-15,art-50}.md`
- Create: `knowledge/crosswalk/{index,soc2-iso42001,iso42001-ai-act}.md`
- Create: `knowledge/policies/{llm-prompt-logged,llm-hardcoded-key,llm-unbounded-call,llm-no-ai-disclosure,ai-inventory-complete}.md`
- Create: `knowledge/stack/ai-assistant.md`, `knowledge/ai-inventory.md`
- Modify: `knowledge/index.md`, `knowledge/controls/index.md`, `knowledge/policies/index.md`, `knowledge/stack/index.md`, `knowledge/log.md`
- Modify: `tests/test_bundle_conformance.py`

**Interfaces:**
- Declarations (the whole mapping this spec adds):

| Concept | Type | Control tags | `rule_ids` |
|---|---|---|---|
| `policies/llm-prompt-logged` | Semgrep Rule | `iso42001:a.7`, `eu-ai-act:art-12` | `semgrep:llm-prompt-logged` |
| `policies/llm-hardcoded-key` | Semgrep Rule | `cc6.1`, `iso42001:a.6` | `semgrep:llm-hardcoded-key` |
| `policies/llm-unbounded-call` | Semgrep Rule | `iso42001:a.6` | `semgrep:llm-unbounded-call` |
| `policies/llm-no-ai-disclosure` | Semgrep Rule | `eu-ai-act:art-50` | `semgrep:llm-no-ai-disclosure` |
| `policies/ai-inventory-complete` | Rego Policy | `iso42001:a.4` | `conftest:ai_inventory_complete` |

- `applies_when: {risk_tier: [high]}` on Art. 9, 10, 12, 13, 14, 15. Art. 50 and all ISO controls always apply.
- No concept declares `semgrep:llm-output-unreviewed-write` (AI-6 stays a gap).

**Clean-room check while drafting:** every `# Intent` below is written in our own words. Do not replace any of it with text from ISO/IEC 42001. The ISO clause ids and group names must be confirmed against a licensed copy in Task 6; if a group name differs, fix `title`, `description`, and the index line, never paste the standard's wording.

- [ ] **Step 1: Write the conformance tests first.** Apply to `tests/test_bundle_conformance.py`: replace `test_bundle_has_the_five_controls` and add the applicability and crosswalk checks.

```python
def test_bundle_has_the_expected_controls() -> None:
    keys = {c.key for c in BUNDLE.controls()}
    assert {k for k in keys if k.startswith("soc2:")} == {f"soc2:{c}" for c in ("cc6.1", "cc6.6", "cc7.1", "cc7.2", "cc8.1")}
    assert {k for k in keys if k.startswith("iso42001:")} == {f"iso42001:a.{n}" for n in range(4, 10)}
    assert {k for k in keys if k.startswith("eu-ai-act:")} == {f"eu-ai-act:art-{n}" for n in (9, 10, 12, 13, 14, 15, 50)}


def test_applies_when_uses_known_fields_and_tiers() -> None:
    for control in BUNDLE.controls():
        applies_when = control.frontmatter.get("applies_when") or {}
        assert set(applies_when) <= {"risk_tier"}, control.path
        assert set(applies_when.get("risk_tier", [])) <= RISK_TIERS, control.path


def test_high_risk_articles_declare_their_tier() -> None:
    for n in (9, 10, 12, 13, 14, 15):
        assert BUNDLE.control(f"eu-ai-act:art-{n}").frontmatter["applies_when"] == {"risk_tier": ["high"]}
    assert "applies_when" not in BUNDLE.control("eu-ai-act:art-50").frontmatter


def test_inventory_tier_is_known() -> None:
    inventory = yaml.safe_load((KNOWLEDGE.parent / "app" / "ai-inventory.yaml").read_text())
    assert inventory["risk_tier"] in RISK_TIERS


def test_every_crosswalk_links_controls_across_frameworks() -> None:
    pairs = BUNDLE.crosswalk_pairs()
    assert {cw for cw, _, _ in pairs} == {c.id for c in BUNDLE.of_type("Crosswalk")}
    for cw, left, right in pairs:
        a, b = BUNDLE.concepts[left], BUNDLE.concepts[right]
        assert a.framework != b.framework, f"{cw}: {left} and {right} are in the same framework"
```

Also add, next to `TYPES`:

```python
RISK_TIERS = {"minimal", "limited", "high"}
```

Run: `uv run pytest tests/test_bundle_conformance.py -q`
Expected: FAIL on `test_bundle_has_the_expected_controls`, `test_inventory_tier_is_known` (if Task 3 is not merged), and the crosswalk test.

- [ ] **Step 2: ISO/IEC 42001 controls.** One file per Annex A group. `generated.by` records the drafting agent; replace it with the actual model or `human:<name>` if a person writes the file.

`knowledge/controls/iso42001/index.md`:

```markdown
# ISO/IEC 42001 Annex A

Clause ids and group names only; intents are written in our own words.

* [A.4 — Resources for AI systems](a.4.md) - The organization knows and records the resources each AI system depends on.
* [A.5 — Assessing impacts of AI systems](a.5.md) - Effects of an AI system on people and groups are assessed before and during use.
* [A.6 — AI system life cycle](a.6.md) - AI systems are designed, built, deployed, and operated under defined controls.
* [A.7 — Data for AI systems](a.7.md) - Data that enters or leaves an AI system is governed for quality, provenance, and protection.
* [A.8 — Information for interested parties of AI systems](a.8.md) - People affected by an AI system get the information they need about it.
* [A.9 — Use of AI systems](a.9.md) - AI systems are used for their intended purpose, with human oversight where needed.
```

`knowledge/controls/iso42001/a.4.md`:

```markdown
---
type: ISO/IEC 42001 Control
framework: iso42001
title: A.4 — Resources for AI systems
description: The organization knows and records the resources each AI system depends on.
tags: [iso42001, iso42001:a.4]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

Each AI system has an owner and a recorded list of what it depends on: models,
providers, data, tooling, and people. An AI feature that is not in the inventory
is a resource the organization cannot govern.

# Clause

ISO/IEC 42001:2023 Annex A, control group A.4 (Resources for AI systems). Clause id
and group name only; the standard's text is not reproduced here.

# Satisfied by

- [AI inventory is complete](../../policies/ai-inventory-complete.md)

# Applies to

- [AI assistant feature](../../stack/ai-assistant.md)

# Crosswalk

- [SOC 2 ↔ ISO/IEC 42001](../../crosswalk/soc2-iso42001.md)
- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

`knowledge/controls/iso42001/a.5.md`:

```markdown
---
type: ISO/IEC 42001 Control
framework: iso42001
title: A.5 — Assessing impacts of AI systems
description: Effects of an AI system on people and groups are assessed before and during use.
tags: [iso42001, iso42001:a.5]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

Before an AI system goes live, and when it changes, someone assesses how its
outputs could affect the people who use it or are subject to it, and records
the result.

# Clause

ISO/IEC 42001:2023 Annex A, control group A.5 (Assessing impacts of AI systems). Clause id
and group name only; the standard's text is not reproduced here.

# Satisfied by

- None in this bundle yet. The control shows `not-assessed`.

# Applies to

- [AI assistant feature](../../stack/ai-assistant.md)

# Crosswalk

- [SOC 2 ↔ ISO/IEC 42001](../../crosswalk/soc2-iso42001.md)
- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

`knowledge/controls/iso42001/a.6.md`:

```markdown
---
type: ISO/IEC 42001 Control
framework: iso42001
title: A.6 — AI system life cycle
description: AI systems are designed, built, deployed, and operated under defined controls.
tags: [iso42001, iso42001:a.6]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

An AI system is built and run with the same engineering discipline as other
production software: secrets are managed, calls to models are bounded, and
deployment and operation follow documented requirements.

# Clause

ISO/IEC 42001:2023 Annex A, control group A.6 (AI system life cycle). Clause id
and group name only; the standard's text is not reproduced here.

# Satisfied by

- [No hard-coded LLM API keys](../../policies/llm-hardcoded-key.md)
- [Bound every LLM call](../../policies/llm-unbounded-call.md)

# Applies to

- [AI assistant feature](../../stack/ai-assistant.md)

# Crosswalk

- [SOC 2 ↔ ISO/IEC 42001](../../crosswalk/soc2-iso42001.md)
- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

`knowledge/controls/iso42001/a.7.md`:

```markdown
---
type: ISO/IEC 42001 Control
framework: iso42001
title: A.7 — Data for AI systems
description: Data that enters or leaves an AI system is governed for quality, provenance, and protection.
tags: [iso42001, iso42001:a.7]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

Prompts, context, and model outputs are data. They are handled with a defined
purpose, protected like other sensitive data, and not copied into places
(such as logs) where they escape those controls.

# Clause

ISO/IEC 42001:2023 Annex A, control group A.7 (Data for AI systems). Clause id
and group name only; the standard's text is not reproduced here.

# Satisfied by

- [Do not log prompts or completions](../../policies/llm-prompt-logged.md)

# Applies to

- [AI assistant feature](../../stack/ai-assistant.md)

# Crosswalk

- [SOC 2 ↔ ISO/IEC 42001](../../crosswalk/soc2-iso42001.md)
- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

`knowledge/controls/iso42001/a.8.md`:

```markdown
---
type: ISO/IEC 42001 Control
framework: iso42001
title: A.8 — Information for interested parties of AI systems
description: People affected by an AI system get the information they need about it.
tags: [iso42001, iso42001:a.8]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

Users and other affected parties can learn that an AI system is involved, what
it does, and how to raise a concern about it.

# Clause

ISO/IEC 42001:2023 Annex A, control group A.8 (Information for interested parties of AI systems). Clause id
and group name only; the standard's text is not reproduced here.

# Satisfied by

- None in this bundle yet. The control shows `not-assessed`.

# Applies to

- [AI assistant feature](../../stack/ai-assistant.md)

# Crosswalk

- [SOC 2 ↔ ISO/IEC 42001](../../crosswalk/soc2-iso42001.md)
- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

`knowledge/controls/iso42001/a.9.md`:

```markdown
---
type: ISO/IEC 42001 Control
framework: iso42001
title: A.9 — Use of AI systems
description: AI systems are used for their intended purpose, with human oversight where needed.
tags: [iso42001, iso42001:a.9]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

An AI system is used only for the purpose it was assessed for. Where its
output drives an action, a person can review or override that action.

# Clause

ISO/IEC 42001:2023 Annex A, control group A.9 (Use of AI systems). Clause id
and group name only; the standard's text is not reproduced here.

# Satisfied by

- None in this bundle yet. The control shows `not-assessed`.

# Applies to

- [AI assistant feature](../../stack/ai-assistant.md)

# Crosswalk

- [SOC 2 ↔ ISO/IEC 42001](../../crosswalk/soc2-iso42001.md)
- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

- [ ] **Step 3: EU AI Act articles.**

`knowledge/controls/eu-ai-act/index.md`:

```markdown
# EU AI Act (Regulation (EU) 2024/1689)

Articles 9–15 apply to high-risk systems only; `applies_when` records that.

* [Art. 9 — Risk management system](art-9.md) - High-risk AI systems run a documented, continuous risk management process.
* [Art. 10 — Data and data governance](art-10.md) - Training, validation, and test data for high-risk AI systems meet quality criteria.
* [Art. 12 — Record-keeping](art-12.md) - High-risk AI systems automatically log events over their lifetime.
* [Art. 13 — Transparency and provision of information to deployers](art-13.md) - High-risk AI systems come with instructions that let deployers understand and use them.
* [Art. 14 — Human oversight](art-14.md) - High-risk AI systems are designed so that people can oversee them effectively.
* [Art. 15 — Accuracy, robustness and cybersecurity](art-15.md) - High-risk AI systems reach and keep appropriate accuracy, robustness, and security.
* [Art. 50 — Transparency obligations for certain AI systems](art-50.md) - People are told when they interact with an AI system or see AI-generated content.
```

`knowledge/controls/eu-ai-act/art-9.md`:

```markdown
---
type: EU AI Act Article
framework: eu-ai-act
title: Art. 9 — Risk management system
description: High-risk AI systems run a documented, continuous risk management process.
tags: [eu-ai-act, eu-ai-act:art-9]
applies_when:
  risk_tier: [high]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

A provider of a high-risk system identifies, evaluates, and mitigates its
risks through the whole life cycle, and keeps doing so after release.

# Scope

Applies to high-risk AI systems only (Chapter III). The sample app declares
`risk_tier: limited` in `app/ai-inventory.yaml`, so this article reports
`not-applicable`.

# Source

[Regulation (EU) 2024/1689, Article 9](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) (paraphrased).

# Satisfied by

- None in this bundle yet.

# Crosswalk

- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

`knowledge/controls/eu-ai-act/art-10.md`:

```markdown
---
type: EU AI Act Article
framework: eu-ai-act
title: Art. 10 — Data and data governance
description: Training, validation, and test data for high-risk AI systems meet quality criteria.
tags: [eu-ai-act, eu-ai-act:art-10]
applies_when:
  risk_tier: [high]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

The data used to train, validate, and test a high-risk system is governed:
relevant, representative, and examined for bias and gaps.

# Scope

Applies to high-risk AI systems only (Chapter III). The sample app declares
`risk_tier: limited` in `app/ai-inventory.yaml`, so this article reports
`not-applicable`.

# Source

[Regulation (EU) 2024/1689, Article 10](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) (paraphrased).

# Satisfied by

- None in this bundle yet.

# Crosswalk

- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

`knowledge/controls/eu-ai-act/art-12.md`:

```markdown
---
type: EU AI Act Article
framework: eu-ai-act
title: Art. 12 — Record-keeping
description: High-risk AI systems automatically log events over their lifetime.
tags: [eu-ai-act, eu-ai-act:art-12]
applies_when:
  risk_tier: [high]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

A high-risk system records events automatically, so its operation can be
traced after the fact. The records themselves must be protected.

# Scope

Applies to high-risk AI systems only (Chapter III). The sample app declares
`risk_tier: limited` in `app/ai-inventory.yaml`, so this article reports
`not-applicable`.

# Source

[Regulation (EU) 2024/1689, Article 12](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) (paraphrased).

# Satisfied by

- [Do not log prompts or completions](../../policies/llm-prompt-logged.md)

# Crosswalk

- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

`knowledge/controls/eu-ai-act/art-13.md`:

```markdown
---
type: EU AI Act Article
framework: eu-ai-act
title: Art. 13 — Transparency and provision of information to deployers
description: High-risk AI systems come with instructions that let deployers understand and use them.
tags: [eu-ai-act, eu-ai-act:art-13]
applies_when:
  risk_tier: [high]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

A high-risk system ships with clear information on its purpose, accuracy,
limits, and the oversight it needs.

# Scope

Applies to high-risk AI systems only (Chapter III). The sample app declares
`risk_tier: limited` in `app/ai-inventory.yaml`, so this article reports
`not-applicable`.

# Source

[Regulation (EU) 2024/1689, Article 13](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) (paraphrased).

# Satisfied by

- None in this bundle yet.

# Crosswalk

- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

`knowledge/controls/eu-ai-act/art-14.md`:

```markdown
---
type: EU AI Act Article
framework: eu-ai-act
title: Art. 14 — Human oversight
description: High-risk AI systems are designed so that people can oversee them effectively.
tags: [eu-ai-act, eu-ai-act:art-14]
applies_when:
  risk_tier: [high]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

People assigned to oversee a high-risk system can understand its output,
decide not to use it, and stop it.

# Scope

Applies to high-risk AI systems only (Chapter III). The sample app declares
`risk_tier: limited` in `app/ai-inventory.yaml`, so this article reports
`not-applicable`.

# Source

[Regulation (EU) 2024/1689, Article 14](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) (paraphrased).

# Satisfied by

- None in this bundle yet.

# Crosswalk

- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

`knowledge/controls/eu-ai-act/art-15.md`:

```markdown
---
type: EU AI Act Article
framework: eu-ai-act
title: Art. 15 — Accuracy, robustness and cybersecurity
description: High-risk AI systems reach and keep appropriate accuracy, robustness, and security.
tags: [eu-ai-act, eu-ai-act:art-15]
applies_when:
  risk_tier: [high]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

A high-risk system performs consistently, resists errors and misuse, and
is protected against attacks on its inputs and dependencies.

# Scope

Applies to high-risk AI systems only (Chapter III). The sample app declares
`risk_tier: limited` in `app/ai-inventory.yaml`, so this article reports
`not-applicable`.

# Source

[Regulation (EU) 2024/1689, Article 15](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) (paraphrased).

# Satisfied by

- None in this bundle yet.

# Crosswalk

- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

`knowledge/controls/eu-ai-act/art-50.md`:

```markdown
---
type: EU AI Act Article
framework: eu-ai-act
title: Art. 50 — Transparency obligations for certain AI systems
description: People are told when they interact with an AI system or see AI-generated content.
tags: [eu-ai-act, eu-ai-act:art-50]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Intent

When a person interacts with an AI system, or receives content an AI system
generated, they are told so, unless it is obvious from the context.

# Scope

Applies at every risk tier that includes interaction with people, so it
applies to the sample app (`risk_tier: limited`).

# Source

[Regulation (EU) 2024/1689, Article 50](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) (paraphrased).

# Satisfied by

- [Disclose AI-generated output](../../policies/llm-no-ai-disclosure.md)

# Crosswalk

- [ISO/IEC 42001 ↔ EU AI Act](../../crosswalk/iso42001-ai-act.md)
```

- [ ] **Step 4: Guardrails (the declarations).**

`knowledge/policies/llm-prompt-logged.md`:

```markdown
---
type: Semgrep Rule
title: Do not log prompts or completions
description: Prompts and model outputs must not be written to application logs in clear text.
resource: ../../policies/semgrep/llm-prompt-logged.yaml
tags: [semgrep, ai, iso42001:a.7, eu-ai-act:art-12]
rule_ids:
  - semgrep:llm-prompt-logged
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Rule

A logger call whose argument is a prompt or a completion copies user input and
model output into the log pipeline, where retention and access rules for that
data no longer hold.

# Satisfies

- [A.7 — Data for AI systems](../controls/iso42001/a.7.md)
- [Art. 12 — Record-keeping](../controls/eu-ai-act/art-12.md): logging is expected, but the records must be protected; high-risk only

# Enforced at

- Semgrep in CI, using the vendored ruleset in `policies/semgrep/`

# Remediation

Log a request id and a hash of the prompt, not the prompt or the completion.
Keep full transcripts, if needed, in a store with its own access control and retention.
```

`knowledge/policies/llm-hardcoded-key.md`:

```markdown
---
type: Semgrep Rule
title: No hard-coded LLM API keys
description: Model-provider API keys must come from the environment or a secret store.
resource: ../../policies/semgrep/llm-hardcoded-key.yaml
tags: [semgrep, ai, cc6.1, iso42001:a.6]
rule_ids:
  - semgrep:llm-hardcoded-key
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Rule

A string literal assigned to an `*_API_KEY` name puts a credential in source
control, where anyone with read access can use it.

# Satisfies

- [CC6.1 — Logical Access](../controls/cc6.1.md)
- [A.6 — AI system life cycle](../controls/iso42001/a.6.md)

# Enforced at

- Semgrep in CI, using the vendored ruleset in `policies/semgrep/`

# Remediation

Read the key from the environment (for example `os.environ["ANTHROPIC_API_KEY"]`)
or a secret manager, and rotate any key that was committed.
```

`knowledge/policies/llm-unbounded-call.md`:

```markdown
---
type: Semgrep Rule
title: Bound every LLM call
description: Every model call sets both a timeout and a max_tokens limit.
resource: ../../policies/semgrep/llm-unbounded-call.yaml
tags: [semgrep, ai, iso42001:a.6]
rule_ids:
  - semgrep:llm-unbounded-call
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Rule

A model call with no timeout can hang a request worker; a call with no
`max_tokens` bound has no cap on cost or output size.

# Satisfies

- [A.6 — AI system life cycle](../controls/iso42001/a.6.md)

The EU AI Act robustness article (Art. 15) is a high-risk obligation, so this
rule is not declared against it; see the crosswalk for the link.

# Enforced at

- Semgrep in CI, using the vendored ruleset in `policies/semgrep/`

# Remediation

Pass `timeout=` and `max_tokens=` on every `messages.create` call, sized to the
feature's latency and cost budget.
```

`knowledge/policies/llm-no-ai-disclosure.md`:

```markdown
---
type: Semgrep Rule
title: Disclose AI-generated output
description: Responses that carry model output tell the user it is AI-generated.
resource: ../../policies/semgrep/llm-no-ai-disclosure.yaml
tags: [semgrep, ai, eu-ai-act:art-50]
rule_ids:
  - semgrep:llm-no-ai-disclosure
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Rule

A view that returns model output without a disclosure field leaves the client
no way to tell the user that the content was generated by AI.

# Satisfies

- [Art. 50 — Transparency obligations for certain AI systems](../controls/eu-ai-act/art-50.md)

# Enforced at

- Semgrep in CI, using the vendored ruleset in `policies/semgrep/`

# Remediation

Add `"ai_generated": true` to every response that carries model output, and
show it in the client.
```

`knowledge/policies/ai-inventory-complete.md`:

```markdown
---
type: Rego Policy
title: AI inventory is complete
description: Every AI component of the app has an entry in the AI system inventory.
resource: ../../policies/rego/ai_inventory_complete.rego
tags: [opa, conftest, ai, iso42001:a.4]
rule_ids:
  - conftest:ai_inventory_complete
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Rule

`app/ai-inventory.yaml` lists every component with its kind and every
inventoried AI system. A component of kind `assistant` with no system entry is
an AI feature the organization does not govern.

# Satisfies

- [A.4 — Resources for AI systems](../controls/iso42001/a.4.md)

# Enforced at

- Conftest in CI, reading `app/ai-inventory.yaml`

# Remediation

Add a `systems` entry for the component with its owner, model provider, and
purpose, then review its risk tier.
```

- [ ] **Step 5: Crosswalks, the component, and the inventory reference.**

`knowledge/crosswalk/index.md`:

```markdown
# Crosswalk

Navigation links between frameworks. A link never carries a mapping or a status.

* [SOC 2 ↔ ISO/IEC 42001](soc2-iso42001.md) - Navigation links between SOC 2 criteria and ISO/IEC 42001 Annex A groups.
* [ISO/IEC 42001 ↔ EU AI Act](iso42001-ai-act.md) - Navigation links between ISO/IEC 42001 Annex A groups and EU AI Act articles.
```

`knowledge/crosswalk/soc2-iso42001.md`:

```markdown
---
type: Crosswalk
title: SOC 2 ↔ ISO/IEC 42001
description: Navigation links between SOC 2 criteria and ISO/IEC 42001 Annex A groups.
tags: [crosswalk, soc2, iso42001]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Links

Each line links two controls that cover related ground. A link is navigation
only: it never moves a finding or a status from one control to the other.

- [CC6.1 — Logical Access](../controls/cc6.1.md) ↔ [A.6 — AI system life cycle](../controls/iso42001/a.6.md)
- [CC7.2 — Security Monitoring](../controls/cc7.2.md) ↔ [A.6 — AI system life cycle](../controls/iso42001/a.6.md)
- [CC8.1 — Change Management](../controls/cc8.1.md) ↔ [A.6 — AI system life cycle](../controls/iso42001/a.6.md)
```

`knowledge/crosswalk/iso42001-ai-act.md`:

```markdown
---
type: Crosswalk
title: ISO/IEC 42001 ↔ EU AI Act
description: Navigation links between ISO/IEC 42001 Annex A groups and EU AI Act articles.
tags: [crosswalk, iso42001, eu-ai-act]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# Links

Each line links two controls that cover related ground. A link is navigation
only: it never moves a finding or a status from one control to the other.
NIST AI RMF functions are listed for orientation only.

- [A.5 — Assessing impacts of AI systems](../controls/iso42001/a.5.md) ↔ [Art. 9 — Risk management system](../controls/eu-ai-act/art-9.md)
- [A.7 — Data for AI systems](../controls/iso42001/a.7.md) ↔ [Art. 10 — Data and data governance](../controls/eu-ai-act/art-10.md)
- [A.7 — Data for AI systems](../controls/iso42001/a.7.md) ↔ [Art. 12 — Record-keeping](../controls/eu-ai-act/art-12.md)
- [A.8 — Information for interested parties](../controls/iso42001/a.8.md) ↔ [Art. 13 — Transparency to deployers](../controls/eu-ai-act/art-13.md)
- [A.8 — Information for interested parties](../controls/iso42001/a.8.md) ↔ [Art. 50 — Transparency obligations](../controls/eu-ai-act/art-50.md)
- [A.9 — Use of AI systems](../controls/iso42001/a.9.md) ↔ [Art. 14 — Human oversight](../controls/eu-ai-act/art-14.md)
- [A.6 — AI system life cycle](../controls/iso42001/a.6.md) ↔ [Art. 15 — Accuracy, robustness and cybersecurity](../controls/eu-ai-act/art-15.md)

# NIST AI RMF (orientation)

The [NIST AI RMF 1.0](https://doi.org/10.6028/NIST.AI.100-1) functions Govern, Map, Measure, and Manage span
all of the links above. It is not a framework in this bundle.
```

`knowledge/stack/ai-assistant.md`:

```markdown
---
type: Stack Component
title: AI assistant feature
description: DRF views that send widget text to an LLM and return or store the result; never run.
resource: ../../app/assistant/
tags: [ai, django, drf, python, llm]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# What it is

Two views: `summarize` returns a model-written summary of a widget, and
`rewrite_description` stores model output on the widget. Seeded with
AI-governance issues AI-1 to AI-6; see `app/SEEDED.yaml`.

# Controls that apply

- [CC6.1 — Logical Access](../controls/cc6.1.md)
- [A.4 — Resources for AI systems](../controls/iso42001/a.4.md)
- [A.6 — AI system life cycle](../controls/iso42001/a.6.md)
- [A.7 — Data for AI systems](../controls/iso42001/a.7.md)
- [Art. 50 — Transparency obligations for certain AI systems](../controls/eu-ai-act/art-50.md)

# Declared in

- [AI system inventory](../ai-inventory.md)

# Scanned by

- [Semgrep](../scanners/semgrep.md)
- [Conftest](../scanners/conftest.md)
```

`knowledge/ai-inventory.md`:

```markdown
---
type: Reference
title: AI system inventory
description: The inventory file that lists AI components and declares the EU AI Act risk tier.
resource: ../app/ai-inventory.yaml
tags: [ai, inventory, risk-tier]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
---
# What it holds

- `risk_tier`: the declared EU AI Act risk class (`minimal`, `limited`, `high`).
  `map_findings.py` reads it and compares it with each control's `applies_when`.
  A control whose `applies_when` excludes the tier reports `not-applicable`,
  never a gap and never `no-violations-detected`.
- `components`: every app component with its `kind`.
- `systems`: the inventoried AI systems. The
  [AI inventory is complete](policies/ai-inventory-complete.md) policy checks
  that every `assistant` component has one.

# Declared tier

The sample app declares `limited`: the assistant talks to people, so Art. 50
applies, but it is not a high-risk use under Annex III.
```

- [ ] **Step 6: Indexes and log.** Apply:

```diff
diff --git a/knowledge/controls/index.md b/knowledge/controls/index.md
index 1b7058e..d0a9cd8 100644
--- a/knowledge/controls/index.md
+++ b/knowledge/controls/index.md
@@ -1,5 +1,10 @@
 # Controls
 
+SOC 2 criteria are listed here; the AI-governance frameworks have their own folders.
+
+* [ISO/IEC 42001 Annex A](iso42001/) - AI management system controls, by Annex A group
+* [EU AI Act](eu-ai-act/) - Articles of Regulation (EU) 2024/1689 that apply to AI systems
+
 * [CC6.1 — Logical Access](cc6.1.md) - Access to systems and data is restricted to authorized, least-privileged identities.
 * [CC6.6 — System Boundary Protection](cc6.6.md) - Resources are protected from access originating outside the system boundary.
 * [CC7.1 — Vulnerability Detection](cc7.1.md) - Vulnerabilities in code, dependencies, images, and configuration are detected.
diff --git a/knowledge/index.md b/knowledge/index.md
index 104c1e3..65f3420 100644
--- a/knowledge/index.md
+++ b/knowledge/index.md
@@ -10,8 +10,10 @@ invent a mapping.
 
 # Map
 
-* [Controls](controls/) - SOC 2 Trust Services Criteria in scope, mapped to NIST SP 800-53
+* [Controls](controls/) - SOC 2 criteria (mapped to NIST SP 800-53), ISO/IEC 42001 Annex A, and EU AI Act articles in scope
+* [Crosswalk](crosswalk/) - navigation links between frameworks; never a mapping
 * [Stack](stack/) - the sample app and its infrastructure
 * [Policies](policies/) - guardrails (Rego, Semgrep) and the scanner rules that detect each
 * [Scanners](scanners/) - DevSecOps tools and the controls they evidence
+* [AI system inventory](ai-inventory.md) - the declared AI risk tier that decides which controls apply
 * [OSCAL output](oscal/component-definition.md) - the machine-readable output target
diff --git a/knowledge/log.md b/knowledge/log.md
index 5f9b03c..6e8ebf9 100644
--- a/knowledge/log.md
+++ b/knowledge/log.md
@@ -3,4 +3,6 @@
 ## 2026-09-25
 * **Initialization**: Created the bundle: 5 controls, 4 stack components, 4 guardrail policies, 4 scanners, and the OSCAL reference.
 * **Update**: Human review of all concepts; verified recorded.
-* **Update**: Human review of evidenced checks; verified recorded.
\ No newline at end of file
+* **Update**: Human review of evidenced checks; verified recorded.
+## 2026-09-28
+* **Update**: Added ISO/IEC 42001 Annex A (A.4–A.9) and EU AI Act (Art. 9, 10, 12–15, 50) controls, two crosswalks, five AI guardrails, the AI assistant component, and the AI inventory reference. SOC 2 controls gain `framework: soc2`.
diff --git a/knowledge/policies/index.md b/knowledge/policies/index.md
index b1f5547..bf373b5 100644
--- a/knowledge/policies/index.md
+++ b/knowledge/policies/index.md
@@ -2,9 +2,14 @@
 
 Each guardrail declares, in `rule_ids`, every scanner rule that detects a
 violation of it. A concept that declares `rule_ids` carries exactly one
-control tag.
+control tag per framework.
 
 * [Require non-root containers](require-non-root.md) - Containers and images must not run as root.
 * [Deny :latest image tag](deny-latest-tag.md) - Deployments must pin an immutable image tag or digest.
 * [No public buckets](no-public-bucket.md) - Storage buckets must not grant access to allUsers or allAuthenticatedUsers.
 * [DRF writes require authentication](drf-authenticated-writes.md) - API views must not use AllowAny.
+* [Do not log prompts or completions](llm-prompt-logged.md) - Prompts and model outputs must not be written to application logs in clear text.
+* [No hard-coded LLM API keys](llm-hardcoded-key.md) - Model-provider API keys must come from the environment or a secret store.
+* [Bound every LLM call](llm-unbounded-call.md) - Every model call sets both a timeout and a max_tokens limit.
+* [Disclose AI-generated output](llm-no-ai-disclosure.md) - Responses that carry model output tell the user it is AI-generated.
+* [AI inventory is complete](ai-inventory-complete.md) - Every AI component of the app has an entry in the AI system inventory.
diff --git a/knowledge/stack/index.md b/knowledge/stack/index.md
index 8f1605c..3506cb7 100644
--- a/knowledge/stack/index.md
+++ b/knowledge/stack/index.md
@@ -4,3 +4,4 @@
 * [Container image](container.md) - The API's Dockerfile.
 * [Kubernetes manifests](k8s.md) - Deployment and Service for the API.
 * [Terraform module](terraform.md) - Storage bucket and service account for the API.
+* [AI assistant feature](ai-assistant.md) - DRF views that send widget text to an LLM and return or store the result; never run.
```

Make sure `knowledge/log.md` keeps a blank line before the new `## 2026-09-28` heading.

- [ ] **Step 7: Run the suite and the scan.**

Run: `uv run pytest -q`
Expected: exactly **22 failures, all `test_every_concept_is_human_verified[...]`** — one per new concept (6 ISO, 7 AI Act, 5 guardrails, 2 crosswalks, the component, the inventory reference). Anything else failing is a bug to fix now.

Run: `make scan && grep -A3 "## Risk posture" out/report.md`
Expected (CVE counts drift with the Trivy DB; the structure must match):

```
## Risk posture

71 open findings across 8 of 12 controls: 3 critical, 26 high, 25 medium, 12 low, 5 unclassified.
0 controls show no violations. 4 not assessed. 6 not applicable. 42 coverage gaps to triage.
```

- [ ] **Step 8: STOP. Hand off to the repo owner.** Do not commit. Leave the working tree as is and report: the 22 files awaiting review, the Task 6 checklist, and the `make scan` summary above.

---

## Task 6: Human review of the AI governance concepts — HUMAN GATE

**Files:**
- Modify: every concept created in Task 5 (add `verified`)

- [ ] **Step 1: Verify ISO/IEC 42001 clause ids and group names against a licensed copy** of ISO/IEC 42001:2023 Annex A: A.4 Resources for AI systems; A.5 Assessing impacts of AI systems; A.6 AI system life cycle; A.7 Data for AI systems; A.8 Information for interested parties of AI systems; A.9 Use of AI systems. Fix any mismatch in `title`, `description`, and `controls/iso42001/index.md`.

- [ ] **Step 2: Clean-room pass.** Read every `# Intent` and `# Rule` section. Each must be our own words; none may reproduce the standard. EU AI Act text must be paraphrase with the EUR-Lex link.

- [ ] **Step 3: Check each declaration** in the Task 5 table: the rule really detects a violation of that control, and the article's `applies_when` matches its chapter (Art. 9–15 are Chapter III high-risk obligations; Art. 50 is Chapter IV).

- [ ] **Step 4: Record the review** on each of the 22 concepts, under `generated`:

```yaml
verified:
  - by: "human:cdevarenne"
    at: "<ISO-8601 timestamp with offset>"
```

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Log and commit Tasks 5 and 6 together.** Add `* **Update**: Human review of the AI governance concepts; verified recorded.` under `## 2026-09-28` in `knowledge/log.md`, then:

```bash
git add knowledge tests/test_bundle_conformance.py
git commit -m "Add ISO/IEC 42001 and EU AI Act concepts, guardrails, and crosswalks" -m "Closes #<A5>" -m "Closes #<A6>"
```

---

## Task 7: End-to-end integration and refreshed example

**Files:**
- Modify: `tests/test_integration.py`, `examples/report.md`, `docs/screenshots/knowledge-graph.png`

- [ ] **Step 1: Add the AI assertions.** Append to `tests/test_integration.py`:

```python
def test_high_risk_articles_are_not_applicable_at_limited_tier(mapping: dict) -> None:
    high_risk = [f"eu-ai-act:art-{n}" for n in (9, 10, 12, 13, 14, 15)]
    assert {mapping["controls"][k]["status"] for k in high_risk} == {"not-applicable"}
    assert mapping["controls"]["eu-ai-act:art-50"]["status"] == "not-satisfied"


def test_not_applicable_article_keeps_its_finding(mapping: dict) -> None:
    entry = mapping["controls"]["eu-ai-act:art-12"]
    assert [f["rule_id"] for f in entry["findings"]] == ["llm-prompt-logged"]
    assert entry["reason"] == "control-not-applicable"


def test_report_has_a_section_per_framework_and_a_crosswalk(mapping: dict) -> None:
    report = (OUT / "report.md").read_text()
    for heading in ("## SOC 2", "## ISO/IEC 42001", "## EU AI Act", "## Crosswalk", "## Not applicable"):
        assert f"\n{heading}\n" in report, heading


def test_oscal_has_one_source_per_framework(mapping: dict) -> None:
    doc = json.loads((OUT / "oscal" / "component-definition.json").read_text())
    titles = [r["title"] for r in doc["component-definition"]["back-matter"]["resources"]]
    assert [t.split(" ")[0] for t in titles] == ["AICPA", "ISO/IEC", "Regulation"]
```

The parametrized `test_seeded_issue_lands_where_expected` already covers AI-1 to AI-6 from `SEEDED.yaml`.

- [ ] **Step 2: Run the full scan tests.**

Run: `make test-integration`
Expected: `19 passed` (13 seeds + 6 others).

- [ ] **Step 3: Refresh the example report and the graph.**

Run: `make examples && make render`
Then open `out/knowledge-viz.html`, check the new ISO, AI Act, and crosswalk nodes are linked, and replace `docs/screenshots/knowledge-graph.png` with a fresh screenshot.

- [ ] **Step 4: Commit.**

```bash
git add tests/test_integration.py examples/report.md docs/screenshots/knowledge-graph.png
git commit -m "Assert the AI governance seeds end to end and refresh the example report" -m "Closes #<A7>"
```

---

## Task 8: README: AI governance and limits (docs only)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the opening paragraph** so it names all three frameworks: "…maps each finding to a SOC 2 / NIST SP 800-53, ISO/IEC 42001, or EU AI Act control…".

- [ ] **Step 2: Add a section after "How grounding works":**

```markdown
## AI governance

The sample app includes a small LLM feature (`app/assistant/`) seeded with six
AI-governance issues. The bundle maps them to ISO/IEC 42001 Annex A groups and
EU AI Act articles through the same `rule_ids` declarations, keyed
`framework:code` (`iso42001:a.6`, `eu-ai-act:art-50`).

- **Risk-tier applicability.** `app/ai-inventory.yaml` declares the EU AI Act
  risk tier (`limited`). Articles that apply only to high-risk systems carry
  `applies_when: {risk_tier: [high]}` and report `not-applicable`, never a gap
  and never `no-violations-detected`. Their findings stay listed.
- **Crosswalks are navigation.** `knowledge/crosswalk/` links related controls
  across frameworks; the report shows each side's own status. A link never
  moves a finding.
- **Honest gaps.** Seed AI-6 (AI output written without human review) is
  detected but no control claims its rule, so it is a coverage gap.
- **Clean-room.** ISO/IEC 42001 concepts carry clause ids and group names only;
  intents are paraphrased. AI Act articles are paraphrased with EUR-Lex links.
  The OSCAL source for ISO/IEC 42001 is a placeholder: ISO publishes no OSCAL
  catalog.
```

- [ ] **Step 3: Update "Limits".** Rename the heading to `## Limits`, and add:

```markdown
- **Declared risk tier only.** The AI Act tier is read from
  `app/ai-inventory.yaml`; nothing classifies the system. There is no
  conformity assessment, model evaluation, or NIST AI RMF control set
  (crosswalk links only).
```

- [ ] **Step 4: Commit.**

```bash
git add README.md
git commit -m "Document AI governance controls and limits in the README" -m "Docs only; no new tests." -m "Closes #<A8>"
```

---

## Done when (spec §2)

| Spec criterion | Where it is proven |
|---|---|
| 1. Each new seeded AI issue lands on its expected control | `test_seeded_issue_lands_where_expected[AI-1..AI-5]` (Task 7) |
| 2. One seeded AI issue is a coverage gap | `test_seeded_issue_lands_where_expected[AI-6]` expects `gap:no-rule-match` |
| 3. Controls outside the declared tier show `not-applicable` | `test_applicability.py` (Task 2); `test_high_risk_articles_are_not_applicable_at_limited_tier` (Task 7) |
| 4. One report section per framework and a crosswalk table | `test_one_section_per_framework_in_order`, `test_crosswalk_row_shows_each_side_status` (Task 2); integration check (Task 7) |
| 5. OSCAL validates with one `control-implementation` per source | `test_one_control_implementation_per_framework_source` (Task 2); `test_oscal_has_one_source_per_framework` (Task 7) |
| 6. `make test` and `make test-integration` pass | Tasks 6 and 7 |
