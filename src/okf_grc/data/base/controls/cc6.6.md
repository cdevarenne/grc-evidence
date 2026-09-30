---
type: SOC 2 Control
framework: soc2
title: CC6.6 — System Boundary Protection
description: Resources are protected from access originating outside the system boundary.
tags: [soc2, cc6.6, nist-sc-7, nist-sc-8]
generated:
  by: human:cdevarenne
  at: "2026-09-25T15:29:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
---
# Intent

Nothing inside the system boundary is reachable anonymously from outside it,
and data crossing the boundary is protected in transit.

# NIST SP 800-53 mapping

- **SC-7** — Boundary Protection
- **SC-8** — Transmission Confidentiality and Integrity

# Satisfied by

- [No public buckets](../policies/no-public-bucket.md)

# Evidenced by

- [Checkov](../scanners/checkov.md) — IaC boundary checks
- [Conftest](../scanners/conftest.md) — the no-public-bucket policy gate
- [Trivy](../scanners/trivy.md) — public-bucket configuration check
