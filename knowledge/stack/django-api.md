---
type: Stack Component
title: Sample Django / DRF API
description: Minimal widgets REST API; the application code under scan.
resource: ../../app/widgets/
tags: [django, drf, python]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
---
# What it is

A deliberately small Django REST Framework API with seeded, fixable issues so
the scan loop has something real to find. Not a production system.

# Controls that apply

- [CC6.1 — Logical Access](../controls/cc6.1.md)
- [CC7.1 — Vulnerability Detection](../controls/cc7.1.md)

# Scanned by

- [Semgrep](../scanners/semgrep.md)
- [Trivy](../scanners/trivy.md)
