---
type: Scanner Check
title: Log network flows
description: The cluster's VPC flow logs and intranode visibility are enabled.
tags: [terraform, gke, cc7.2]
rule_ids:
  - checkov:CKV_GCP_61
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-01T15:48:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-10-01T15:58:00-07:00"
---
# Rule

Without flow logs, traffic between workloads leaves no record to monitor or
investigate.

# Satisfies

- [CC7.2 — Security Monitoring](../controls/cc7.2.md)

# Enforced at

- Detected by Checkov (listed in `rule_ids`); no rule of this bundle enforces it

# Remediation

Set `enable_intranode_visibility = true` on the cluster and enable flow logs on
its subnetwork.
