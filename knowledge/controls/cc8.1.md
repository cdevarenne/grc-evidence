---
type: SOC 2 Control
framework: soc2
title: CC8.1 — Change Management
description: Changes to infrastructure and software are controlled, reproducible, and reviewed.
tags: [soc2, cc8.1, nist-cm-2, nist-cm-3]
generated:
  by: "human:cdevarenne"
  at: "2026-09-25T15:30:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
  - by: "human:cdevarenne"
    at: "2026-10-01T15:58:00-07:00"
---
# Intent

What is deployed is exactly what was reviewed: artifacts are pinned and
changes pass automated policy gates before release.

# NIST SP 800-53 mapping

- **CM-2** — Baseline Configuration
- **CM-3** — Configuration Change Control

# Satisfied by

- [Deny :latest image tag](../policies/deny-latest-tag.md)
- [Pin images and modules to reviewed sources](../policies/pin-image-provenance.md)

# Evidenced by

- [Conftest](../scanners/conftest.md) — policy gate on manifests
- [Checkov](../scanners/checkov.md) — IaC policy scan
- [Trivy](../scanners/trivy.md) — `:latest` image-tag check
