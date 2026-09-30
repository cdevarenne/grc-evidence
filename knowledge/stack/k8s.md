---
type: Stack Component
title: Kubernetes manifests
description: Deployment and Service for the API.
resource: ../../app/k8s/
tags: [kubernetes]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
---
# What it is

The Deployment and Service that run the API. This is the policy enforcement
point for the Rego guardrails.

# Controls that apply

- [CC6.1 — Logical Access](../controls/cc6.1.md)
- [CC7.2 — Security Monitoring](../controls/cc7.2.md)
- [CC8.1 — Change Management](../controls/cc8.1.md)

# Scanned by

- [Conftest](../scanners/conftest.md)
- [Checkov](../scanners/checkov.md)
- [Trivy](../scanners/trivy.md)
