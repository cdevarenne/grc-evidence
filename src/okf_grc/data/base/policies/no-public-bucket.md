---
type: Rego Policy
title: No public buckets
description: Storage buckets must not grant access to allUsers or allAuthenticatedUsers.
resource: ../../policies/rego/no_public_bucket.rego
tags: [opa, conftest, terraform, cc6.6]
rule_ids:
  - conftest:no_public_bucket
  - checkov:CKV_GCP_28
  - checkov:CKV_GCP_114
  - trivy:GCP-0001
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-25T14:50:00-07:00"
---
# Rule

An IAM binding to `allUsers` or `allAuthenticatedUsers` exposes bucket
contents to anyone on the internet, outside the system boundary.

# Satisfies

- [CC6.6 — System Boundary Protection](../controls/cc6.6.md)

# Enforced at

- Deploy gate: Conftest on Terraform, blocking
- Also detected by Checkov and Trivy (listed in `rule_ids`)

# Remediation

Remove public IAM members from the bucket, grant access to named service
accounts only, and enforce public access prevention on the bucket.
