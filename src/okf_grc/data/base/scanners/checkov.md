---
type: Scanner
title: Checkov
description: Infrastructure-as-code policy scan.
resource: https://github.com/bridgecrewio/checkov
tags: [iac, cc6.6, cc8.1]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-25T14:50:00-07:00"
---
# Covers

Terraform, Kubernetes, and Dockerfile misconfigurations.

# Evidences

- [CC6.6 — System Boundary Protection](../controls/cc6.6.md)
- [CC8.1 — Change Management](../controls/cc8.1.md)

# Rules

Rule-to-control declarations live on guardrail concepts, for example
[No public buckets](../policies/no-public-bucket.md).
