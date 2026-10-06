---
okf_version: "0.2"
base_version: "2.0.1"  # the grc-evidence base bundle these controls, crosswalks, scanners, and generic policies were copied from
---
# OKF-GRC Knowledge Bundle

Knowledge graph that grounds the `grc-continuous-compliance` skill. Every
finding the skill reports must trace to a control concept here. A finding
with no mapped control is a coverage gap to report, never a license to
invent a mapping.

# Map

* [Controls](controls/) - SOC 2 criteria (mapped to NIST SP 800-53), ISO/IEC 42001 Annex A, and EU AI Act articles in scope
* [Crosswalk](crosswalk/) - navigation links between frameworks; never a mapping
* [Stack](stack/) - the sample app and its infrastructure
* [Policies](policies/) - guardrails (Rego, Semgrep) and the scanner rules that detect each
* [Scanners](scanners/) - DevSecOps tools and the controls they evidence
* [Suppressions](suppressions/) - reviewed, expiring false positives and accepted risks; never hidden
* [AI system inventory](ai-inventory.md) - the declared AI risk tier that decides which controls apply
* [OSCAL output](oscal/component-definition.md) - the machine-readable output target
