---
type: Scanner Check
title: Harden the container runtime
description: Containers run with a seccomp profile, a read-only root file system, every Linux capability dropped, an explicit security context, no mounted service-account token they do not need, and a high non-root UID and GID.
tags: [kubernetes, cc6.1]
rule_ids:
  - checkov:CKV_K8S_22
  - checkov:CKV_K8S_29
  - checkov:CKV_K8S_31
  - checkov:CKV_K8S_38
  - checkov:CKV_K8S_40
  - trivy:KSV-0003
  - trivy:KSV-0004
  - trivy:KSV-0014
  - trivy:KSV-0020
  - trivy:KSV-0021
  - trivy:KSV-0030
  - trivy:KSV-0104
  - trivy:KSV-0106
  - trivy:KSV-0118
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-01T15:48:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-10-01T15:58:00-07:00"
  - by: "human:cdevarenne"
    at: "2026-10-12T17:45:00-07:00"
---
# Rule

Least privilege inside the pod: each setting removes a capability an attacker
who gains code execution would otherwise have (system calls, Linux
capabilities, writes to the image, a cluster credential, a UID shared with the
host). A container left on the default security context keeps all of them.

# Satisfies

- [CC6.1 — Logical Access](../controls/cc6.1.md)

# Enforced at

- Detected by Checkov and Trivy (listed in `rule_ids`); no rule of this bundle enforces it

# Remediation

Set a `securityContext` on every pod and container: `seccompProfile:
{type: RuntimeDefault}`, `readOnlyRootFilesystem: true`, `capabilities:
{drop: [ALL]}` (add back only `NET_BIND_SERVICE` if the container binds a port
below 1024), `runAsUser` and `runAsGroup` above 10000; set `automountServiceAccountToken: false` unless the
workload calls the Kubernetes API.
