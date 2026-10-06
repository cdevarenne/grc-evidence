---
type: Scanner Check
title: Least-privilege access to GKE
description: Cluster access uses Google identities and groups, not client certificates; nodes use a dedicated service account and the GKE metadata server.
tags: [terraform, gke, cc6.1]
rule_ids:
  - checkov:CKV_GCP_13
  - checkov:CKV_GCP_65
  - checkov:CKV_GCP_69
  - trivy:GCP-0050
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-01T15:48:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-10-01T15:58:00-07:00"
---
# Rule

Client certificates cannot be revoked one by one; the default compute service
account and the node metadata endpoint give every pod broad project
credentials.

# Satisfies

- [CC6.1 — Logical Access](../controls/cc6.1.md)

# Enforced at

- Detected by Checkov and Trivy (listed in `rule_ids`); no rule of this bundle enforces it

# Remediation

Disable `client_certificate_config`, manage RBAC through Google Groups
(`authenticator_groups_config`), give node pools a dedicated least-privilege
service account, and set `workload_metadata_config { mode = "GKE_METADATA" }`.
