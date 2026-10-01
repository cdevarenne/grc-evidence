---
type: Scanner Check
title: Declare health checks
description: Containers declare liveness and readiness probes, and images a HEALTHCHECK.
tags: [kubernetes, docker, a1.1]
rule_ids:
  - checkov:CKV_DOCKER_2
  - checkov:CKV_K8S_8
  - checkov:CKV_K8S_9
  - trivy:DS-0026
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-01T15:48:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-10-01T15:58:00-07:00"
---
# Rule

Probes let the platform route around and restart a failed component, so the
service keeps the capacity it was planned with.

# Satisfies

- [A1.1 — Capacity Management](../controls/a1.1.md)

# Enforced at

- Detected by Checkov and Trivy (listed in `rule_ids`); no rule of this bundle enforces it

# Remediation

Add `livenessProbe` and `readinessProbe` to every container in the
Deployment, and a `HEALTHCHECK` to the Dockerfile for runtimes that use it.
