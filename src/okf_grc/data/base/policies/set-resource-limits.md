---
type: Scanner Check
title: Set resource requests and limits
description: Every container declares CPU and memory requests and limits.
tags: [kubernetes, a1.1]
rule_ids:
  - checkov:CKV_K8S_10
  - checkov:CKV_K8S_11
  - checkov:CKV_K8S_12
  - checkov:CKV_K8S_13
  - trivy:KSV-0011
  - trivy:KSV-0015
  - trivy:KSV-0016
  - trivy:KSV-0018
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-01T15:48:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-10-01T15:58:00-07:00"
---
# Rule

Requests let the scheduler plan capacity; limits stop one workload from
starving the others on its node.

# Satisfies

- [A1.1 — Capacity Management](../controls/a1.1.md)

# Enforced at

- Detected by Checkov and Trivy (listed in `rule_ids`); no rule of this bundle enforces it

# Remediation

Set `resources.requests` and `resources.limits` for `cpu` and `memory` on
every container, sized from observed use.
