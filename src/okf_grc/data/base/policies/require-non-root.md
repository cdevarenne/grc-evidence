---
type: Rego Policy
title: Require non-root containers
description: Containers and images must not run as root.
resource: ../../policies/rego/require_non_root.rego
tags: [opa, conftest, kubernetes, cc6.1]
rule_ids:
  - conftest:require_non_root
  - checkov:CKV_K8S_23
  - checkov:CKV_DOCKER_3
  - trivy:KSV-0012
  - trivy:KSV-0105
  - trivy:DS-0002
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-25T14:50:00-07:00"
---
# Rule

A process running as root inside a container turns any code-execution bug into
root on the container and widens the path to the node. Workloads must set
`runAsNonRoot: true` and images must switch to a non-root `USER`.

# Satisfies

- [CC6.1 — Logical Access](../controls/cc6.1.md)

# Enforced at

- Deploy gate: Conftest in CI, blocking
- Also detected by Checkov and Trivy (listed in `rule_ids`)

# Remediation

Add a non-root `USER` to the Dockerfile and set `securityContext.runAsNonRoot: true`
(with a non-zero `runAsUser`) on every container in the Deployment.
