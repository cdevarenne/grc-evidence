---
type: Scanner Check
title: Harden the container runtime
description: Containers run with a seccomp profile, a read-only root file system, no mounted service-account token they do not need, and a high non-root UID and GID.
tags: [kubernetes, cc6.1]
rule_ids:
  - checkov:CKV_K8S_22
  - checkov:CKV_K8S_29
  - checkov:CKV_K8S_31
  - checkov:CKV_K8S_38
  - checkov:CKV_K8S_40
  - trivy:KSV-0014
  - trivy:KSV-0020
  - trivy:KSV-0021
  - trivy:KSV-0030
  - trivy:KSV-0104
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-01T15:48:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-10-01T15:58:00-07:00"
---
# Rule

Least privilege inside the pod: each setting removes a capability an attacker
who gains code execution would otherwise have (system calls, writes to the
image, a cluster credential, a UID shared with the host).

# Satisfies

- [CC6.1 — Logical Access](../controls/cc6.1.md)

# Enforced at

- Detected by Checkov and Trivy (listed in `rule_ids`); no rule of this bundle enforces it

# Remediation

Set a `securityContext` on every pod and container: `seccompProfile:
{type: RuntimeDefault}`, `readOnlyRootFilesystem: true`, `runAsUser` and
`runAsGroup` above 10000; set `automountServiceAccountToken: false` unless the
workload calls the Kubernetes API.
