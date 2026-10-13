---
type: Scanner Check
title: Restrict pod traffic with a NetworkPolicy
description: Every pod is selected by a NetworkPolicy, so the traffic it may receive is declared rather than open to the whole cluster.
tags: [kubernetes, cc6.6]
rule_ids:
  - checkov:CKV2_K8S_6
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-12T17:16:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-10-12T17:45:00-07:00"
---
# Rule

Without a NetworkPolicy, Kubernetes lets any pod in the cluster reach any other
pod. A policy that selects the pod sets its boundary: only the sources it names
may connect.

# Satisfies

- [CC6.6 — System Boundary Protection](../controls/cc6.6.md)

# Enforced at

- Detected by Checkov (listed in `rule_ids`); no rule of this bundle enforces it

# Remediation

Add a NetworkPolicy whose `podSelector` matches the workload, with `ingress`
rules for the callers it serves; start from a namespace-wide default-deny
policy so that a new pod is closed until it is given its own.
