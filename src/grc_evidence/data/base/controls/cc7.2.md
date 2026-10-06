---
type: SOC 2 Control
framework: soc2
title: CC7.2 — Security Monitoring
description: System components are monitored for anomalous and malicious activity.
tags: [soc2, cc7.2, nist-si-4, nist-au-6]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
  - by: "human:cdevarenne"
    at: "2026-10-01T15:58:00-07:00"
---
# Intent

Running workloads are monitored so anomalies and attacks are detected and
acted on.

# NIST SP 800-53 mapping

- **SI-4** — System Monitoring
- **AU-6** — Audit Record Review, Analysis, and Reporting

# Satisfied by

- [Log network flows](../policies/network-flow-logs.md)

# Evidenced by

- [Checkov](../scanners/checkov.md) — whether flow logging is configured

Only configuration is checked: that monitoring data is collected, not that
anyone reviews it. No scanner here evidences runtime detection.
