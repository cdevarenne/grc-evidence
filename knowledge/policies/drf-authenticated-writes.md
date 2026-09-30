---
type: Semgrep Rule
title: DRF writes require authentication
description: API views must not use AllowAny.
resource: ../../policies/semgrep/drf-allowany.yaml
tags: [semgrep, django, cc6.1]
rule_ids:
  - semgrep:drf-allowany
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
---
# Rule

`AllowAny` on a DRF view lets unauthenticated callers use every action the
view exposes, including create, update, and delete.

# Satisfies

- [CC6.1 — Logical Access](../controls/cc6.1.md)

# Enforced at

- Semgrep in CI, using the vendored ruleset in `policies/semgrep/`

# Remediation

Replace `AllowAny` with an authenticated permission class (for example
`IsAuthenticated`, or `IsAuthenticatedOrReadOnly` for public reads).
