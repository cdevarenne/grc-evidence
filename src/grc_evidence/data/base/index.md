---
okf_version: "0.2"
---
# OKF-GRC Base Bundle

The reusable part of an grc-evidence knowledge bundle, shipped with the engine:
controls, crosswalks, scanners, and the generic guardrails with the scanner
rules each one declares. `grc init` copies it into an adopter's `knowledge/`,
next to the concepts only that adopter can write: its stack, its suppressions,
and its AI inventory. A finding reaches a control only through a `rule_ids`
declaration; one with no declaration is a coverage gap.

# Map

* [Controls](controls/) - SOC 2 criteria (mapped to NIST SP 800-53), ISO/IEC 42001 Annex A, and EU AI Act articles
* [Crosswalk](crosswalk/) - navigation links between frameworks; never a mapping
* [Policies](policies/) - generic guardrails (Rego, Semgrep) and the scanner rules that detect each
* [Scanners](scanners/) - DevSecOps tools and the controls they evidence
* [OSCAL output](oscal/component-definition.md) - the machine-readable output target
