---
type: Scanner Check
title: Isolate workloads in their own namespace
description: Workloads do not run in the default namespace.
tags: [kubernetes, cc6.1]
rule_ids:
  - checkov:CKV_K8S_21
  - trivy:KSV-0110
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-01T15:48:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-10-01T15:58:00-07:00"
---
# Rule

The default namespace is shared by anything deployed without one, so its
RBAC bindings and network policies cannot be scoped to a single application.

# Satisfies

- [CC6.1 — Logical Access](../controls/cc6.1.md)

# Enforced at

- Detected by Checkov and Trivy (listed in `rule_ids`); no rule of this bundle enforces it

# Remediation

Create a namespace for the application and set `metadata.namespace` on every
manifest (or deploy with `-n`), then scope RBAC and network policy to it.
