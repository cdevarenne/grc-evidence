# Mini Spec D — OSCAL Assessment Plan: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `make scan` also writes `out/oscal/assessment-plan.json`, a schema-valid OSCAL 1.2.3 assessment plan built from the same bundle, and `assessment-results.json` imports it instead of pointing at `#assessment-plan-not-modeled`.

**Architecture:** `run_scan.py` exposes its five scanner runs as data (`ScannerRun`, `scanner_runs()`) plus a `tools.lock` reader (`load_pins()`), so the plan describes the commands that actually run. `to_oscal.assessment_plan()` reads the bundle, the mapping (for applicability at the declared AI risk tier), and the pins. The results link to the plan by the relative href `assessment-plan.json`. The one remaining placeholder is the plan's required `import-ssp` (`#system-security-plan-not-modeled`).

**Tech Stack:** unchanged (Python 3.14, PyYAML, pytest, jsonschema; OSCAL 1.2.3).

**Spec:** `docs/superpowers/specs/2026-09-28-mini-spec-d-oscal-assessment-plan.md` (reviewed 2026-09-28: all three §8 recommendations accepted — in scope = every applicable control; `import-ssp` placeholder; relative `import-ap.href`).

**Provenance:** every diff in this plan was produced from a prototype on 2026-09-28 and replayed in order from `main` (`b6fead9`) as four commits: the unit suite went 395 → 398 → 410 → 412 passed, and after Task 3 `make test-integration` passed 23 tests against the pinned scanners. The vendored schema's SHA-256 was checked against the NIST v1.2.3 release asset.

## Global Constraints

- Everything in the v1 plan's Global Constraints still holds.
- **Commits:** trunk-based on `main`, authored by `cdevarenne`. **Never add a `Co-Authored-By` trailer.** Short subject, `Closes #N` body line. Every commit ships tests; docs-only commits say so.
- **No invented facts.** Every planned activity is a real `run_scan.py` run; every version comes from `tools.lock`; every activity's related controls come from `rule_ids` declarations.
- **Deterministic.** UUIDs are UUIDv5 over stable inputs; the plan's own UUID depends on `--now`, like the results'.
- **No LLM, no paid step, no human gate.**

## Task order

Tasks 1 → 3 are sequential (each consumes the previous). Task 4 is docs.

## Task 0: Tracking issues (no commit)

- [x] **Step 1:** One issue per task: #40 (D1), #41 (D2), #42 (D3), #43 (D4).

---

## Task 1: Vendor the schema; scanner runs as data

**Files:**
- Create: `tests/fixtures/oscal/oscal_assessment-plan_schema.json` (NIST release asset, unmodified)
- Modify: `.claude/skills/grc-continuous-compliance/scripts/run_scan.py`
- Test: `tests/test_run_scan.py`

**Interfaces:**
- Produces: `CONFTEST_PATTERNS` (target-relative globs Conftest checks); `ScannerRun` (frozen dataclass: `tool, title, argv, in_target, pin, normalize`); `scanner_runs(target_dir, conftest_inputs) -> list[ScannerRun]` in execution order; `load_pins(lock: Path) -> dict[str, str]`.
- `scan()` behavior is unchanged: same argv, same working directories, same findings.

- [ ] **Step 1: Vendor the schema.**

```bash
curl -sSL -o tests/fixtures/oscal/oscal_assessment-plan_schema.json \
  https://github.com/usnistgov/OSCAL/releases/download/v1.2.3/oscal_assessment-plan_schema.json
sha256sum tests/fixtures/oscal/oscal_assessment-plan_schema.json
# ea687b9d0ab1d84c9cb11ee0a5e22b17956fe892ee93f5acca937bef81d23ea2
```

- [ ] **Step 2: Write the failing tests.**

```diff
diff --git a/tests/test_run_scan.py b/tests/test_run_scan.py
index bc7bc86..6ab3c78 100644
--- a/tests/test_run_scan.py
+++ b/tests/test_run_scan.py
@@ -6,14 +6,17 @@ from typing import Any
 import pytest
 
 from run_scan import (
+    CONFTEST_PATTERNS,
     ScanError,
     dedupe,
+    load_pins,
     normalize_checkov,
     normalize_conftest,
     normalize_semgrep,
     normalize_trivy,
     run_tool,
     scan,
+    scanner_runs,
 )
 
 OUTPUT = Path(__file__).parent / "fixtures" / "scanner_output"
@@ -134,3 +137,22 @@ def test_semgrep_errors_fail_the_scan() -> None:
 def test_scan_rejects_targets_outside_the_repo(tmp_path: Path, target: str) -> None:
     with pytest.raises(ScanError, match="--target"):
         scan(tmp_path, target)
+
+
+def test_scanner_runs_cover_every_tool_with_a_pin() -> None:
+    runs = scanner_runs("app", ["app/k8s/deployment.yaml"])
+    assert [r.tool for r in runs] == ["semgrep", "trivy", "trivy", "checkov", "conftest"]
+    pins = load_pins(Path(__file__).parent.parent / "tools.lock")
+    assert all(r.pin in pins for r in runs)
+    assert runs[-1].argv[-1] == "app/k8s/deployment.yaml"
+    assert [r.in_target for r in runs] == [False, False, False, True, False]
+
+
+def test_conftest_patterns_include_the_ai_inventory() -> None:
+    assert "ai-inventory.yaml" in CONFTEST_PATTERNS
+
+
+def test_load_pins_skips_comments_and_blank_lines(tmp_path: Path) -> None:
+    lock = tmp_path / "tools.lock"
+    lock.write_text("# pins\n\nSEMGREP_VERSION=1.0.0\nOKF_COMMIT=abc\n", encoding="utf-8")
+    assert load_pins(lock) == {"SEMGREP_VERSION": "1.0.0", "OKF_COMMIT": "abc"}
```

- [ ] **Step 3: Run them; expect an ImportError** (`CONFTEST_PATTERNS`, `load_pins`, `scanner_runs`).

```bash
uv run pytest tests/test_run_scan.py -q
```

- [ ] **Step 4: Implement.**

```diff
diff --git a/.claude/skills/grc-continuous-compliance/scripts/run_scan.py b/.claude/skills/grc-continuous-compliance/scripts/run_scan.py
index 587df42..3e856ad 100644
--- a/.claude/skills/grc-continuous-compliance/scripts/run_scan.py
+++ b/.claude/skills/grc-continuous-compliance/scripts/run_scan.py
@@ -6,13 +6,16 @@ import argparse
 import json
 import shutil
 import subprocess
-from collections.abc import Callable
+from collections.abc import Callable, Sequence
+from dataclasses import dataclass
 from pathlib import Path
 from typing import Any
 
 Finding = dict[str, Any]
 SEVERITIES = ("critical", "high", "medium", "low", "info", "unknown")
 _SEMGREP_SEVERITY = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}
+# Files Conftest checks, relative to the scan target.
+CONFTEST_PATTERNS = ("k8s/**/*.yaml", "k8s/**/*.yml", "infra/**/*.tf", "ai-inventory.yaml")
 
 
 class ScanError(RuntimeError):
@@ -115,25 +118,45 @@ def _check_target(repo: Path, target_dir: str) -> None:
         raise ScanError(f"--target {target_dir!r} must be a directory inside the repo root {repo}")
 
 
+@dataclass(frozen=True)
+class ScannerRun:
+    """One scanner invocation. The assessment plan reads these, so it cannot drift from what runs."""
+
+    tool: str
+    title: str
+    argv: tuple[str, ...]
+    in_target: bool  # run with cwd = the scan target; otherwise the repo root
+    pin: str  # the tools.lock key holding this scanner's version
+    normalize: Callable[[Any, str], list[Finding]]
+
+
+def scanner_runs(target_dir: str, conftest_inputs: Sequence[str]) -> list[ScannerRun]:
+    """The five scanner runs over `target_dir`, in execution order."""
+    return [
+        ScannerRun("semgrep", "Semgrep code scan", ("semgrep", "scan", "--config", "policies/semgrep", "--metrics=off", "--json", "--quiet", target_dir), False, "SEMGREP_VERSION", normalize_semgrep),
+        ScannerRun("trivy", "Trivy misconfiguration scan", ("trivy", "config", "--quiet", "--format", "json", target_dir), False, "TRIVY_VERSION", normalize_trivy),
+        ScannerRun("trivy", "Trivy dependency vulnerability scan", ("trivy", "fs", "--quiet", "--scanners", "vuln", "--format", "json", target_dir), False, "TRIVY_VERSION", normalize_trivy),
+        ScannerRun("checkov", "Checkov infrastructure-as-code scan", ("checkov", "-d", ".", "--framework", "terraform", "kubernetes", "dockerfile", "-o", "json", "--quiet", "--compact"), True, "CHECKOV_VERSION", normalize_checkov),
+        ScannerRun("conftest", "Conftest policy check", ("conftest", "test", "--all-namespaces", "--no-color", "-o", "json", "-p", "policies/rego", *conftest_inputs), False, "CONFTEST_VERSION", normalize_conftest),
+    ]
+
+
+def load_pins(lock: Path) -> dict[str, str]:
+    """`KEY=value` lines of tools.lock; comments and blank lines are skipped."""
+    lines = [ln for ln in lock.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
+    return dict(ln.split("=", 1) for ln in lines)
+
+
 def scan(repo: Path, target_dir: str) -> list[Finding]:
     """Run all four scanners over `repo/target_dir` and return deduplicated findings."""
     _check_target(repo, target_dir)
     target = repo / target_dir
     conftest_inputs = sorted(
-        p.relative_to(repo).as_posix()
-        for pattern in ("k8s/**/*.yaml", "k8s/**/*.yml", "infra/**/*.tf", "ai-inventory.yaml")
-        for p in target.glob(pattern)
+        p.relative_to(repo).as_posix() for pattern in CONFTEST_PATTERNS for p in target.glob(pattern)
     )
-    runs: list[tuple[str, list[str], Path, Callable[[Any, str], list[Finding]]]] = [
-        ("semgrep", ["semgrep", "scan", "--config", "policies/semgrep", "--metrics=off", "--json", "--quiet", target_dir], repo, normalize_semgrep),
-        ("trivy", ["trivy", "config", "--quiet", "--format", "json", target_dir], repo, normalize_trivy),
-        ("trivy", ["trivy", "fs", "--quiet", "--scanners", "vuln", "--format", "json", target_dir], repo, normalize_trivy),
-        ("checkov", ["checkov", "-d", ".", "--framework", "terraform", "kubernetes", "dockerfile", "-o", "json", "--quiet", "--compact"], target, normalize_checkov),
-        ("conftest", ["conftest", "test", "--all-namespaces", "--no-color", "-o", "json", "-p", "policies/rego", *conftest_inputs], repo, normalize_conftest),
-    ]
     findings: list[Finding] = []
-    for tool, argv, cwd, normalize in runs:
-        findings += normalize(run_tool(tool, argv, cwd), target_dir)
+    for run in scanner_runs(target_dir, conftest_inputs):
+        findings += run.normalize(run_tool(run.tool, list(run.argv), target if run.in_target else repo), target_dir)
     return dedupe(findings)
 
 
```

- [ ] **Step 5: Run the suite.** Expect `398 passed`.

```bash
uv run pytest -q
```

- [ ] **Step 6: Commit.**

```bash
git add tests/fixtures/oscal/oscal_assessment-plan_schema.json tests/test_run_scan.py .claude/skills/grc-continuous-compliance/scripts/run_scan.py
git commit -m "Vendor the OSCAL assessment-plan schema; expose scanner runs as data" -m "…

Closes #40"
```

---

## Task 2: `assessment_plan()`

**Files:**
- Modify: `.claude/skills/grc-continuous-compliance/scripts/to_oscal.py`
- Test: `tests/test_to_oscal.py`

**Interfaces:**
- Consumes: Task 1 (`CONFTEST_PATTERNS`, `scanner_runs`); `MAX_SUPPRESSION_DAYS` from `okf_lib`.
- Produces: `assessment_plan(bundle, mapping, now, pins, target="app") -> {"assessment-plan": …}`; constants `NO_SSP_HREF`, `PROP_NS`, `SUPPRESSION_POLICY`, `GROUNDING_RULE`.
- Contents (spec §4):
  - `reviewed-controls`: one selection per framework, every control whose mapping status is not `not-applicable`; `remarks` names the excluded keys.
  - `local-definitions.activities`: one per `ScannerRun`, with a `method: TEST` prop, a namespaced `tool-version` prop from the pins, one step holding the exact command, and `related-controls` = in-scope controls some concept declares that tool's rules for. The Trivy config and Trivy fs runs share the tool name `trivy`, so both list every control a Trivy rule evidences.
  - `local-definitions.components` and `assessment-subjects`: the stack components, UUIDs from the same `_uuid("component", id)` as the component definition. A bundle with no components selects subjects with `include-all`.
  - `terms-and-conditions`: `rules-of-engagement` (suppression policy) and `methodology` (grounding rule).
  - `assessment-assets`: one component per scanner tool, titled with its version; one platform (`make scan`) using them.
  - `tasks`: one `action` task associating every activity with the subjects.
- Not yet wired into `main()` or the results (Task 3).

- [ ] **Step 1: Write the failing tests.**

```diff
diff --git a/tests/test_to_oscal.py b/tests/test_to_oscal.py
index 5c355f9..f120f05 100644
--- a/tests/test_to_oscal.py
+++ b/tests/test_to_oscal.py
@@ -6,10 +6,12 @@ import pytest
 from map_findings import map_findings
 from okf_lib import Bundle, load_bundle
 from oscal_schema import validate
-from to_oscal import assessment_results, component_definition
+from run_scan import load_pins
+from to_oscal import NO_SSP_HREF, assessment_plan, assessment_results, component_definition
 
 FIXTURES = Path(__file__).parent / "fixtures"
 NOW = "2026-09-25T12:00:00+00:00"
+PINS = load_pins(Path(__file__).parent.parent / "tools.lock")
 
 
 @pytest.fixture
@@ -171,3 +173,108 @@ def test_reviewed_controls_are_grouped_by_framework() -> None:
     (result,) = assessment_results(ai, mapping, NOW)["assessment-results"]["results"]
     selections = result["reviewed-controls"]["control-selections"]
     assert [s["description"].split(" ")[0] for s in selections] == ["AICPA", "ISO/IEC", "Regulation"]
+
+
+def _plan(bundle: Bundle, mapping: dict) -> dict:
+    return assessment_plan(bundle, mapping, NOW, PINS)["assessment-plan"]
+
+
+def _codes(selections: list[dict]) -> list[str]:
+    return [c["control-id"] for s in selections for c in s["include-controls"]]
+
+
+def test_assessment_plan_is_schema_valid(bundle: Bundle, mapping: dict) -> None:
+    validate(assessment_plan(bundle, mapping, NOW, PINS), "oscal_assessment-plan_schema.json")
+    ai, ai_mapping = _ai()
+    validate(assessment_plan(ai, ai_mapping, NOW, PINS), "oscal_assessment-plan_schema.json")
+
+
+def test_assessment_plan_is_deterministic(bundle: Bundle, mapping: dict) -> None:
+    assert assessment_plan(bundle, mapping, NOW, PINS) == assessment_plan(bundle, mapping, NOW, PINS)
+    assert _plan(bundle, mapping)["uuid"] != assessment_plan(bundle, mapping, "2026-09-26T12:00:00+00:00", PINS)[
+        "assessment-plan"
+    ]["uuid"]
+
+
+def test_plan_imports_the_ssp_placeholder(bundle: Bundle, mapping: dict) -> None:
+    assert _plan(bundle, mapping)["import-ssp"]["href"] == NO_SSP_HREF == "#system-security-plan-not-modeled"
+
+
+def test_plan_scopes_every_applicable_control_including_unevidenced(bundle: Bundle, mapping: dict) -> None:
+    planned = _codes(_plan(bundle, mapping)["reviewed-controls"]["control-selections"])
+    assert planned == ["cc6.1", "cc7.1", "cc7.2", "cc8.1"]  # cc7.2 has no scanner: planned, not assessed
+
+
+def test_plan_excludes_not_applicable_controls() -> None:
+    ai, mapping = _ai()
+    reviewed = _plan(ai, mapping)["reviewed-controls"]
+    assert "art-12" not in _codes(reviewed["control-selections"])
+    assert "art-50" in _codes(reviewed["control-selections"])
+    assert reviewed["remarks"] == "Not applicable at the declared AI risk tier: eu-ai-act:art-12"
+
+
+def test_plan_components_share_uuids_with_the_component_definition(bundle: Bundle, mapping: dict) -> None:
+    plan = _plan(bundle, mapping)
+    cd = component_definition(bundle, NOW)["component-definition"]["components"]
+    planned = [c["uuid"] for c in plan["local-definitions"]["components"]]
+    assert planned == [c["uuid"] for c in cd]
+    (subjects,) = plan["assessment-subjects"]
+    assert [s["subject-uuid"] for s in subjects["include-subjects"]] == planned
+
+
+def test_plan_has_one_activity_per_scanner_run_with_its_pinned_version(bundle: Bundle, mapping: dict) -> None:
+    activities = _plan(bundle, mapping)["local-definitions"]["activities"]
+    versions = [next(p["value"] for p in a["props"] if p["name"] == "tool-version") for a in activities]
+    pins = [PINS[k] for k in ("SEMGREP_VERSION", "TRIVY_VERSION", "TRIVY_VERSION", "CHECKOV_VERSION", "CONFTEST_VERSION")]
+    assert versions == pins
+    assert activities[0]["steps"][0]["description"].startswith("`semgrep scan --config policies/semgrep")
+    assert len({a["uuid"] for a in activities}) == 5
+
+
+def test_activity_related_controls_come_from_rule_declarations(bundle: Bundle, mapping: dict) -> None:
+    by_title = {a["title"]: a for a in _plan(bundle, mapping)["local-definitions"]["activities"]}
+    related = {t: _codes(a.get("related-controls", {}).get("control-selections", [])) for t, a in by_title.items()}
+    declared = {
+        tool: sorted({k.partition(":")[2] for c in bundle.concepts.values() for e in c.rule_ids
+                      if e.startswith(f"{tool}:") for k in c.control_keys if bundle.control(k)})
+        for tool in ("semgrep", "trivy", "checkov", "conftest")
+    }
+    assert related["Semgrep code scan"] == declared["semgrep"]
+    assert related["Checkov infrastructure-as-code scan"] == declared["checkov"]
+    assert "cc7.2" not in {c for codes in related.values() for c in codes}
+
+
+def test_plan_states_the_suppression_policy_and_grounding_rule(bundle: Bundle, mapping: dict) -> None:
+    parts = {p["title"]: p["prose"] for p in _plan(bundle, mapping)["terms-and-conditions"]["parts"]}
+    assert "exactly" in parts["Suppression policy"] and "90 days" in parts["Suppression policy"]
+    assert "human owner" in parts["Suppression policy"] and "`verified`" in parts["Suppression policy"]
+    assert "coverage gap" in parts["Grounding rule"]
+
+
+def test_one_task_runs_every_activity_against_every_subject(bundle: Bundle, mapping: dict) -> None:
+    plan = _plan(bundle, mapping)
+    (task,) = plan["tasks"]
+    assert task["type"] == "action"
+    assert [a["activity-uuid"] for a in task["associated-activities"]] == [
+        a["uuid"] for a in plan["local-definitions"]["activities"]
+    ]
+    assert task["subjects"] == plan["assessment-subjects"]
+
+
+def test_platform_uses_one_component_per_pinned_tool(bundle: Bundle, mapping: dict) -> None:
+    assets = _plan(bundle, mapping)["assessment-assets"]
+    assert [c["title"] for c in assets["components"]] == [
+        f"semgrep {PINS['SEMGREP_VERSION']}", f"trivy {PINS['TRIVY_VERSION']}",
+        f"checkov {PINS['CHECKOV_VERSION']}", f"conftest {PINS['CONFTEST_VERSION']}",
+    ]
+    (platform,) = assets["assessment-platforms"]
+    assert [u["component-uuid"] for u in platform["uses-components"]] == [c["uuid"] for c in assets["components"]]
+
+
+def test_plan_without_components_selects_all_subjects(tmp_path: Path) -> None:
+    (tmp_path / "controls").mkdir()
+    (tmp_path / "controls/cc6.1.md").write_text("---\ntype: SOC 2 Control\ntags: [cc6.1]\n---\n", encoding="utf-8")
+    b = load_bundle(tmp_path)
+    doc = assessment_plan(b, map_findings(b, []), NOW, PINS)
+    validate(doc, "oscal_assessment-plan_schema.json")
+    assert doc["assessment-plan"]["assessment-subjects"][0]["include-all"] == {}
```

- [ ] **Step 2: Run them; expect an ImportError** (`NO_SSP_HREF`, `assessment_plan`).

```bash
uv run pytest tests/test_to_oscal.py -q
```

- [ ] **Step 3: Implement.**

```diff
diff --git a/.claude/skills/grc-continuous-compliance/scripts/to_oscal.py b/.claude/skills/grc-continuous-compliance/scripts/to_oscal.py
index 2d9942f..7bbfe65 100644
--- a/.claude/skills/grc-continuous-compliance/scripts/to_oscal.py
+++ b/.claude/skills/grc-continuous-compliance/scripts/to_oscal.py
@@ -9,7 +9,8 @@ from datetime import UTC, datetime
 from pathlib import Path
 from typing import Any
 
-from okf_lib import COMPONENT_TYPE, FRAMEWORK_TYPES, Bundle, Concept, load_bundle
+from okf_lib import COMPONENT_TYPE, FRAMEWORK_TYPES, MAX_SUPPRESSION_DAYS, Bundle, Concept, load_bundle
+from run_scan import CONFTEST_PATTERNS, scanner_runs
 
 OSCAL_VERSION = "1.2.3"
 DOC_VERSION = "0.1.0"
@@ -33,6 +34,21 @@ SOURCES: dict[str, Json] = {
     },
 }
 NO_AP_HREF = "#assessment-plan-not-modeled"
+NO_SSP_HREF = "#system-security-plan-not-modeled"
+# Namespace for this repo's own props (OSCAL reserves un-namespaced names for NIST-defined ones).
+PROP_NS = "https://github.com/cdevarenne/okf-grc-skill/ns/oscal"
+SUPPRESSION_POLICY = (
+    "A finding may be suppressed only by a suppression concept in the knowledge bundle that matches it exactly "
+    "(tool, rule id, target, and optionally a message fragment; no wildcards), names a human owner and a reason, "
+    "carries a human `verified` entry, and expires at most {days} days after approval. A false positive leaves "
+    "the control's status and is named in the results' remarks; an accepted risk keeps the control not-satisfied "
+    "and is recorded as a deviation-approved risk. An expired suppression no longer applies."
+)
+GROUNDING_RULE = (
+    "A finding maps to a control only through a `rule_ids` declaration in the knowledge bundle. A finding no "
+    "declaration covers is a coverage gap, recorded as an open risk, never as a control finding. A clean "
+    "automated scan evidences a control but never attests it."
+)
 
 
 def _uuid(*parts: str) -> str:
@@ -103,6 +119,123 @@ def component_definition(bundle: Bundle, now: str) -> Json:
     }
 
 
+def _component(comp: Concept) -> Json:
+    """A stack component with the same UUID as in the component-definition."""
+    return {
+        "uuid": _uuid("component", comp.id),
+        "type": "software",
+        "title": comp.title,
+        "description": comp.description or comp.title,
+        "status": {"state": "operational"},
+    }
+
+
+def _evidenced_by(bundle: Bundle, key: str) -> set[str]:
+    """Tools whose rules some concept declares for this control."""
+    return {entry.partition(":")[0] for c in bundle.declaring(key) for entry in c.rule_ids}
+
+
+def assessment_plan(bundle: Bundle, mapping: Json, now: str, pins: dict[str, str], target: str = "app") -> Json:
+    """What the automated scan intends to assess: every applicable control, the scanner runs, the components.
+
+    In scope is every control not excluded by the declared AI risk tier, including controls no scanner
+    evidences; a planned control the results mark not-assessed is a coverage gap at the control level.
+    """
+    in_scope = sorted(key for key, c in mapping["controls"].items() if c["status"] != "not-applicable")
+    excluded = sorted(key for key, c in mapping["controls"].items() if c["status"] == "not-applicable")
+    runs = scanner_runs(target, [f"{target}/{p}" for p in CONFTEST_PATTERNS])
+    activities = []
+    for run in runs:
+        command = " ".join(run.argv)
+        activity: Json = {
+            "uuid": _uuid("activity", command),
+            "title": run.title,
+            "description": f"Run {run.tool} {pins[run.pin]} over `{target}` and normalize its JSON output to findings.",
+            "props": [
+                {"name": "method", "value": "TEST"},
+                {"name": "tool-version", "ns": PROP_NS, "value": pins[run.pin]},
+            ],
+            "steps": [
+                {
+                    "uuid": _uuid("step", command),
+                    "title": "Run the scanner",
+                    "description": f"`{command}` (working directory: {'the scan target' if run.in_target else 'the repository root'})",
+                }
+            ],
+        }
+        if selections := _control_selections(bundle, [k for k in in_scope if run.tool in _evidenced_by(bundle, k)]):
+            activity["related-controls"] = {"control-selections": selections}
+        activities.append(activity)
+    components = [_component(comp) for comp in bundle.of_type(COMPONENT_TYPE)]
+    subjects = [
+        {
+            "type": "component",
+            "description": "The stack components described in the knowledge bundle.",
+            **(
+                {"include-subjects": [{"subject-uuid": c["uuid"], "type": "component"} for c in components]}
+                if components
+                else {"include-all": {}}
+            ),
+        }
+    ]
+    tools = {run.tool: pins[run.pin] for run in runs}
+    tool_components = [
+        {
+            "uuid": _uuid("tool", tool),
+            "type": "software",
+            "title": f"{tool} {version}",
+            "description": f"{tool}, pinned to {version} in tools.lock.",
+            "props": [{"name": "tool-version", "ns": PROP_NS, "value": version}],
+            "status": {"state": "operational"},
+        }
+        for tool, version in tools.items()
+    ]
+    reviewed: Json = {
+        "description": "Every control applicable at the declared AI risk tier, including controls no scanner evidences.",
+        "control-selections": _control_selections(bundle, in_scope),
+    }
+    if excluded:
+        reviewed["remarks"] = f"Not applicable at the declared AI risk tier: {', '.join(excluded)}"
+    plan: Json = {
+        "uuid": _uuid("assessment-plan", now),
+        "metadata": _metadata("okf-grc-skill automated assessment plan", now),
+        "import-ssp": {"href": NO_SSP_HREF, "remarks": "System security plan not modeled; see docs/oscal-subset.md."},
+        "local-definitions": {"activities": activities},
+        "terms-and-conditions": {
+            "parts": [
+                {"name": "rules-of-engagement", "title": "Suppression policy",
+                 "prose": SUPPRESSION_POLICY.format(days=MAX_SUPPRESSION_DAYS)},
+                {"name": "methodology", "title": "Grounding rule", "prose": GROUNDING_RULE},
+            ]
+        },
+        "reviewed-controls": reviewed,
+        "assessment-subjects": subjects,
+        "assessment-assets": {
+            "components": tool_components,
+            "assessment-platforms": [
+                {
+                    "uuid": _uuid("platform", "make-scan"),
+                    "title": "`make scan` pipeline, scanners pinned in tools.lock",
+                    "uses-components": [{"component-uuid": c["uuid"]} for c in tool_components],
+                }
+            ],
+        },
+        "tasks": [
+            {
+                "uuid": _uuid("task", "automated-scan"),
+                "type": "action",
+                "title": "Automated compliance scan",
+                "description": "Run every scanner activity, then map findings to controls through the knowledge bundle.",
+                "associated-activities": [{"activity-uuid": a["uuid"], "subjects": subjects} for a in activities],
+                "subjects": subjects,
+            }
+        ],
+    }
+    if components:
+        plan["local-definitions"]["components"] = components
+    return {"assessment-plan": plan}
+
+
 def _observation(f: Json, now: str) -> Json:
     return {
         "uuid": _uuid("observation", _finding_key(f)),
```

- [ ] **Step 4: Run the suite and lint.** Expect `410 passed`.

```bash
uv run pytest -q && uvx ruff check .claude tests
```

- [ ] **Step 5: Commit** with `Closes #41`.

---

## Task 3: The results import the plan

**Files:**
- Modify: `.claude/skills/grc-continuous-compliance/scripts/to_oscal.py` (`AP_HREF`, `import-ap`, `main()` with `--lock` and `--target`)
- Modify: `Makefile` (`to_oscal.py … --target app`)
- Test: `tests/test_to_oscal.py`, `tests/test_integration.py`

**Interfaces:**
- `AP_HREF = "assessment-plan.json"` replaces `NO_AP_HREF`; `import-ap` is `{"href": AP_HREF}` with no remarks.
- `to_oscal.py` writes `component-definition.json`, `assessment-plan.json`, `assessment-results.json`; `--lock` (default `tools.lock`) and `--target` (default `app`).
- Invariant, tested on both fixture bundles: the results' reviewed controls ⊆ the plan's.

- [ ] **Step 1: Write the failing tests.**

```diff
diff --git a/tests/test_to_oscal.py b/tests/test_to_oscal.py
index f120f05..3f2cd30 100644
--- a/tests/test_to_oscal.py
+++ b/tests/test_to_oscal.py
@@ -7,7 +7,7 @@ from map_findings import map_findings
 from okf_lib import Bundle, load_bundle
 from oscal_schema import validate
 from run_scan import load_pins
-from to_oscal import NO_SSP_HREF, assessment_plan, assessment_results, component_definition
+from to_oscal import AP_HREF, NO_SSP_HREF, assessment_plan, assessment_results, component_definition
 
 FIXTURES = Path(__file__).parent / "fixtures"
 NOW = "2026-09-25T12:00:00+00:00"
@@ -69,6 +69,11 @@ def test_output_is_deterministic(bundle: Bundle, mapping: dict) -> None:
     assert component_definition(bundle, NOW) == component_definition(bundle, NOW)
 
 
+def test_results_import_the_plan_next_to_them(bundle: Bundle, mapping: dict) -> None:
+    assert assessment_results(bundle, mapping, NOW)["assessment-results"]["import-ap"] == {"href": AP_HREF}
+    assert AP_HREF == "assessment-plan.json"
+
+
 def test_validator_rejects_missing_required_field(bundle: Bundle, mapping: dict) -> None:
     from jsonschema import ValidationError
 
@@ -205,6 +210,14 @@ def test_plan_scopes_every_applicable_control_including_unevidenced(bundle: Bund
     assert planned == ["cc6.1", "cc7.1", "cc7.2", "cc8.1"]  # cc7.2 has no scanner: planned, not assessed
 
 
+def test_results_review_a_subset_of_the_plan() -> None:
+    for b, m in ((load_bundle(FIXTURES / "bundle"), None), _ai()):
+        m = m or map_findings(b, json.loads((FIXTURES / "findings.json").read_text()))
+        (result,) = assessment_results(b, m, NOW)["assessment-results"]["results"]
+        reviewed = set(_codes(result["reviewed-controls"]["control-selections"]))
+        assert reviewed <= set(_codes(_plan(b, m)["reviewed-controls"]["control-selections"]))
+
+
 def test_plan_excludes_not_applicable_controls() -> None:
     ai, mapping = _ai()
     reviewed = _plan(ai, mapping)["reviewed-controls"]
```
```diff
diff --git a/tests/test_integration.py b/tests/test_integration.py
index d382a3d..8bfced8 100644
--- a/tests/test_integration.py
+++ b/tests/test_integration.py
@@ -82,7 +82,16 @@ def test_no_suppression_is_unused(mapping: dict) -> None:
 def test_outputs_exist_and_oscal_validates(mapping: dict) -> None:
     assert (OUT / "report.md").read_text().startswith("# Compliance Scan Report")
     validate(json.loads((OUT / "oscal" / "component-definition.json").read_text()), "oscal_component_schema.json")
-    validate(json.loads((OUT / "oscal" / "assessment-results.json").read_text()), "oscal_assessment-results_schema.json")
+    validate(json.loads((OUT / "oscal" / "assessment-plan.json").read_text()), "oscal_assessment-plan_schema.json")
+    results = json.loads((OUT / "oscal" / "assessment-results.json").read_text())
+    validate(results, "oscal_assessment-results_schema.json")
+    assert (OUT / "oscal" / results["assessment-results"]["import-ap"]["href"]).is_file()
+
+
+def test_plan_names_the_monitoring_control_the_results_leave_unassessed(mapping: dict) -> None:
+    plan = json.loads((OUT / "oscal" / "assessment-plan.json").read_text())["assessment-plan"]
+    planned = {c["control-id"] for s in plan["reviewed-controls"]["control-selections"] for c in s["include-controls"]}
+    assert "cc7.2" in planned and "art-12" not in planned
 
 
 def test_monitoring_control_is_not_assessed(mapping: dict) -> None:
```

- [ ] **Step 2: Run the unit tests; expect an ImportError** (`AP_HREF`).

- [ ] **Step 3: Implement.**

```diff
diff --git a/.claude/skills/grc-continuous-compliance/scripts/to_oscal.py b/.claude/skills/grc-continuous-compliance/scripts/to_oscal.py
index 7bbfe65..b4f54b1 100644
--- a/.claude/skills/grc-continuous-compliance/scripts/to_oscal.py
+++ b/.claude/skills/grc-continuous-compliance/scripts/to_oscal.py
@@ -1,4 +1,4 @@
-"""Render a control mapping as OSCAL 1.2.3 component-definition + assessment-results (documented subset)."""
+"""Render a control mapping as OSCAL 1.2.3 component-definition, assessment-plan, and assessment-results (documented subset)."""
 
 from __future__ import annotations
 
@@ -10,7 +10,7 @@ from pathlib import Path
 from typing import Any
 
 from okf_lib import COMPONENT_TYPE, FRAMEWORK_TYPES, MAX_SUPPRESSION_DAYS, Bundle, Concept, load_bundle
-from run_scan import CONFTEST_PATTERNS, scanner_runs
+from run_scan import CONFTEST_PATTERNS, load_pins, scanner_runs
 
 OSCAL_VERSION = "1.2.3"
 DOC_VERSION = "0.1.0"
@@ -33,7 +33,7 @@ SOURCES: dict[str, Json] = {
         "href": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
     },
 }
-NO_AP_HREF = "#assessment-plan-not-modeled"
+AP_HREF = "assessment-plan.json"  # relative: the OSCAL files are written side by side in out/oscal/
 NO_SSP_HREF = "#system-security-plan-not-modeled"
 # Namespace for this repo's own props (OSCAL reserves un-namespaced names for NIST-defined ones).
 PROP_NS = "https://github.com/cdevarenne/okf-grc-skill/ns/oscal"
@@ -353,7 +353,7 @@ def assessment_results(bundle: Bundle, mapping: Json, now: str) -> Json:
         "assessment-results": {
             "uuid": _uuid("assessment-results", now),
             "metadata": _metadata("okf-grc-skill automated assessment", now),
-            "import-ap": {"href": NO_AP_HREF, "remarks": "Assessment plan not modeled in v1; see docs/oscal-subset.md."},
+            "import-ap": {"href": AP_HREF},
             "results": [result],
         }
     }
@@ -364,6 +364,8 @@ def main() -> None:
     parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
     parser.add_argument("--out", type=Path, default=Path("out"))
     parser.add_argument("--now", default=datetime.now(UTC).isoformat(timespec="seconds"))
+    parser.add_argument("--lock", type=Path, default=Path("tools.lock"), help="pinned scanner versions")
+    parser.add_argument("--target", default="app", help="scan target, relative to the repo root")
     args = parser.parse_args()
     bundle = load_bundle(args.knowledge)
     mapping = json.loads((args.out / "mapping.json").read_text(encoding="utf-8"))
@@ -371,6 +373,7 @@ def main() -> None:
     oscal_dir.mkdir(parents=True, exist_ok=True)
     for name, doc in (
         ("component-definition.json", component_definition(bundle, args.now)),
+        ("assessment-plan.json", assessment_plan(bundle, mapping, args.now, load_pins(args.lock), args.target)),
         ("assessment-results.json", assessment_results(bundle, mapping, args.now)),
     ):
         (oscal_dir / name).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
```
```diff
diff --git a/Makefile b/Makefile
index 2c8ed74..66161bc 100644
--- a/Makefile
+++ b/Makefile
@@ -17,7 +17,7 @@ bootstrap:
 scan:
 	$(PY) $(SCRIPTS)/run_scan.py --target app --out out
 	$(PY) $(SCRIPTS)/map_findings.py --knowledge knowledge --out out
-	$(PY) $(SCRIPTS)/to_oscal.py --knowledge knowledge --out out
+	$(PY) $(SCRIPTS)/to_oscal.py --knowledge knowledge --out out --target app
 	$(PY) $(SCRIPTS)/render_report.py --knowledge knowledge --out out
 
 narrate:
```

- [ ] **Step 4: Run everything.** Expect `412 passed`, then `23 passed` for integration, and three files in `out/oscal/`.

```bash
make test && make test-integration && ls out/oscal
```

- [ ] **Step 5: Commit** with `Closes #42`.

---

## Task 4: Docs (docs only)

**Files:** `docs/oscal-subset.md`, `README.md`, `.claude/skills/grc-continuous-compliance/SKILL.md`

```diff
diff --git a/docs/oscal-subset.md b/docs/oscal-subset.md
index d1826a3..918aab9 100644
--- a/docs/oscal-subset.md
+++ b/docs/oscal-subset.md
@@ -1,7 +1,8 @@
 # OSCAL subset emitted
 
-`to_oscal.py` emits OSCAL **1.2.3** JSON. Both documents validate against the
-NIST JSON schemas vendored in `tests/fixtures/oscal/`. This is a documented
+`to_oscal.py` emits OSCAL **1.2.3** JSON: a component definition, an assessment
+plan, and assessment results, side by side in `out/oscal/`. All three validate
+against the NIST JSON schemas vendored in `tests/fixtures/oscal/`. This is a documented
 subset, not a complete OSCAL implementation.
 
 ## component-definition.json
@@ -14,12 +15,32 @@ subset, not a complete OSCAL implementation.
 | `control-implementations[].implemented-requirements[]` | one per linked control that some concept declares rules for; `control-id` is the code within that framework's source (`cc6.1`, `a.6`, `art-50`) |
 | `control-implementations[].source` | `#<uuid>` of that framework's back-matter resource: "AICPA Trust Services Criteria (SOC 2)"; "ISO/IEC 42001:2023 Annex A (placeholder …)"; "Regulation (EU) 2024/1689 (EU AI Act)" with an `rlinks` href to EUR-Lex |
 
+## assessment-plan.json
+
+What the scan intends to assess. Props this repo defines use the namespace
+`https://github.com/cdevarenne/okf-grc-skill/ns/oscal`.
+
+| Field | Source |
+|---|---|
+| `import-ssp.href` | **placeholder** `#system-security-plan-not-modeled`: no system security plan is modeled |
+| `local-definitions.components[]` | one per `Stack Component` concept, with the same UUID as in the component definition |
+| `local-definitions.activities[]` | one per scanner run in `run_scan.py` (Semgrep; Trivy config; Trivy fs; Checkov; Conftest): a step with the exact command, a `tool-version` prop from `tools.lock`, a `method` prop `TEST`, and `related-controls` = the in-scope controls that some concept declares that tool's rules for |
+| `terms-and-conditions.parts[]` | the suppression policy (`rules-of-engagement`) and the grounding rule (`methodology`) |
+| `reviewed-controls` | one `control-selection` per framework: **every control applicable at the declared AI risk tier**, including controls no scanner evidences; `remarks` names the not-applicable ones |
+| `assessment-subjects[]` | the stack components, selected by UUID |
+| `assessment-assets` | one component per scanner, titled with its pinned version; one platform (`make scan`) that uses them |
+| `tasks[]` | one `action` task, "Automated compliance scan", associating every activity with every subject |
+
+A control in the plan that the results mark `not-assessed` is a coverage gap
+at the control level: it was intended but no scanner evidences it. Trivy's two
+runs share one tool name, so each lists every control a Trivy rule evidences.
+
 ## assessment-results.json
 
 | Field | Source |
 |---|---|
-| `import-ap.href` | **placeholder** `#assessment-plan-not-modeled`: v1 has no assessment plan |
-| `results[0].reviewed-controls` | one `control-selection` per framework, described by the framework's source title; includes every control whose status is not `not-assessed` or `not-applicable` |
+| `import-ap.href` | `assessment-plan.json`, the plan written next to it (relative, so the files travel together) |
+| `results[0].reviewed-controls` | one `control-selection` per framework, described by the framework's source title; includes every control whose status is not `not-assessed` or `not-applicable` (always a subset of the plan's) |
 | `results[0].observations[]` | one per scanner finding; `methods: [TEST]` |
 | `results[0].findings[]` | one per control with open violations; `target.status.state` is always `not-satisfied` |
 | `results[0].risks[]` | one per unmapped finding, titled "Coverage gap: …", `status: open`; and one per accepted-risk suppression, titled "Accepted risk: …", `status: deviation-approved`, with the owner, expiry, and reason in its description |
@@ -27,7 +48,9 @@ subset, not a complete OSCAL implementation.
 
 ## Deliberately not modeled
 
-- Assessment plan, SSP, POA&M, and profiles.
+- SSP, POA&M, and profiles. The assessment plan's required `import-ssp` is
+  therefore a placeholder.
+- Manual test procedures: every planned activity is an automated scanner run.
 - A machine-readable SOC 2 catalog: the Trust Services Criteria are not
   published as an OSCAL catalog, so `control-id` values are the criterion codes.
 - Parties, roles, and responsible-parties.
```
```diff
diff --git a/README.md b/README.md
index 894ddee..bf7e171 100644
--- a/README.md
+++ b/README.md
@@ -64,6 +64,26 @@ optionally a message substring; there are no wildcards, and an accepted risk on
 a coverage gap is rejected when the bundle loads. `map_findings.py --today`
 sets the date used for expiry.
 
+## OSCAL output
+
+`make scan` writes three OSCAL 1.2.3 documents to `out/oscal/`, each validated
+against the NIST schema in the tests:
+
+- **`component-definition.json`**: the stack components and the controls each
+  one implements, one source per framework.
+- **`assessment-plan.json`**: what the scan intends to assess. Every control
+  applicable at the declared AI risk tier (including controls no scanner
+  evidences), one activity per scanner run with its exact command and pinned
+  version, the stack components as subjects, and the suppression policy and
+  grounding rule as terms and conditions.
+- **`assessment-results.json`**: what the scan found. It imports the plan, so a
+  control the plan names and the results mark `not-assessed` reads as a gap
+  in coverage, not a pass.
+
+The plan's required link to a system security plan is a placeholder
+(`#system-security-plan-not-modeled`); no SSP is modeled. See
+[`docs/oscal-subset.md`](docs/oscal-subset.md).
+
 ## LLM step and cost
 
 The scan, the mapping, OSCAL, and every number in the report are deterministic.
```
```diff
diff --git a/.claude/skills/grc-continuous-compliance/SKILL.md b/.claude/skills/grc-continuous-compliance/SKILL.md
index 42f4387..f878b1a 100644
--- a/.claude/skills/grc-continuous-compliance/SKILL.md
+++ b/.claude/skills/grc-continuous-compliance/SKILL.md
@@ -30,7 +30,8 @@ description: >
 2. **Scan and map.** Run `make scan`. It writes:
    - `out/findings.json`: normalized findings `{tool, rule_id, severity, target, message, tags}`
    - `out/mapping.json`: per-control status plus unmapped findings with a reason
-   - `out/oscal/component-definition.json`, `out/oscal/assessment-results.json`
+   - `out/oscal/component-definition.json`, `out/oscal/assessment-plan.json`,
+     `out/oscal/assessment-results.json` (the results import the plan)
    - `out/report.md`: the deterministic report
 3. **Review.** Read `out/report.md` and `out/mapping.json`. Summarize for the
    user: controls not satisfied, the highest-severity findings, coverage gaps,
```

- [ ] **Step 1:** `uv run pytest tests/test_skill_md.py -q` still passes.
- [ ] **Step 2: Commit** with `Closes #43` and "Docs only; no new tests."

---

## Done when (spec §2)

| # | Criterion | Where |
|---|---|---|
| 1 | Plan validates against the NIST 1.2.3 schema | `test_assessment_plan_is_schema_valid`, integration |
| 2 | `import-ap.href` is `assessment-plan.json`; old placeholder gone | `test_results_import_the_plan_next_to_them`, integration resolves the href |
| 3 | Per-framework in-scope controls; results ⊆ plan | `test_plan_scopes_every_applicable_control_including_unevidenced`, `test_results_review_a_subset_of_the_plan` |
| 4 | One activity per run, command and pinned version, related controls | `test_plan_has_one_activity_per_scanner_run_with_its_pinned_version`, `test_activity_related_controls_come_from_rule_declarations` |
| 5 | Subjects = stack components, same UUIDs | `test_plan_components_share_uuids_with_the_component_definition` |
| 6 | Suppression policy in terms and conditions | `test_plan_states_the_suppression_policy_and_grounding_rule` |
| 7 | Deterministic; `make test`, `make test-integration` pass | `test_assessment_plan_is_deterministic`; Task 3 Step 4 |
