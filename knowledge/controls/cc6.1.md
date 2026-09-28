---
type: SOC 2 Control
framework: soc2
title: CC6.1 — Logical Access
description: Access to systems and data is restricted to authorized, least-privileged identities.
tags: [soc2, cc6.1, nist-ac-2, nist-ac-3, nist-ac-6]
generated:
  by: human:cdevarenne
  at: "2026-09-25T15:28:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-25T15:31:00-07:00"
---
# Intent

Only authenticated, authorized identities reach protected functions and data,
and workloads run with the least privilege they need.

# NIST SP 800-53 mapping

- **AC-2** — Account Management
- **AC-3** — Access Enforcement
- **AC-6** — Least Privilege

# Satisfied by

- [Require non-root containers](../policies/require-non-root.md)
- [DRF writes require authentication](../policies/drf-authenticated-writes.md)

# Evidenced by

- [Semgrep](../scanners/semgrep.md) — authorization rules in application code
- [Checkov](../scanners/checkov.md) — root-container checks on the Dockerfile and manifests
- [Conftest](../scanners/conftest.md) — the require-non-root policy gate
- [Trivy](../scanners/trivy.md) — root-user configuration checks

# Applies to

- [Sample Django / DRF API](../stack/django-api.md)
- [Container image](../stack/container.md)
- [Kubernetes manifests](../stack/k8s.md)
