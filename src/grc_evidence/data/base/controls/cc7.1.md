---
type: SOC 2 Control
framework: soc2
title: CC7.1 — Vulnerability Detection
description: Vulnerabilities in code, dependencies, images, and configuration are detected.
tags: [soc2, cc7.1, nist-ra-5, nist-si-2]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
---
# Intent

Known vulnerabilities across the software supply chain are detected before
they can be exploited: source, third-party dependencies, and container images.

# NIST SP 800-53 mapping

- **RA-5** — Vulnerability Monitoring and Scanning
- **SI-2** — Flaw Remediation

# Evidenced by

- [Trivy](../scanners/trivy.md) — dependency CVEs from `trivy fs`. Built
  container images are not scanned in v1, so image CVEs are not evidenced.
