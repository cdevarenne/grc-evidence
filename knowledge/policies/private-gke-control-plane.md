---
type: Scanner Check
title: Keep the GKE cluster private
description: The cluster's nodes and control plane are private, the API is reachable only from authorized networks, and network policy is enforced.
tags: [terraform, gke, cc6.6]
rule_ids:
  - checkov:CKV_GCP_12
  - checkov:CKV_GCP_20
  - checkov:CKV_GCP_25
  - checkov:CKV_GCP_64
  - trivy:GCP-0059
  - trivy:GCP-0061
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-01T15:48:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-10-01T15:58:00-07:00"
---
# Rule

Public nodes and a control plane open to the internet put the cluster
boundary at the cluster API itself.

# Satisfies

- [CC6.6 — System Boundary Protection](../controls/cc6.6.md)

# Enforced at

- Detected by Checkov and Trivy (listed in `rule_ids`); no rule of this bundle enforces it

# Remediation

Set `private_cluster_config` (private nodes and endpoint), a
`master_authorized_networks_config` listing only operator networks, and
`network_policy { enabled = true }` on the `google_container_cluster`.
