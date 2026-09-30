---
type: Rego Policy
title: Deny :latest image tag
description: Deployments must pin an immutable image tag or digest.
resource: ../../policies/rego/deny_latest_tag.rego
tags: [opa, conftest, kubernetes, cc8.1]
rule_ids:
  - conftest:deny_latest_tag
  - checkov:CKV_K8S_14
  - trivy:KSV-0013
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-25T14:50:00-07:00"
---
# Rule

`:latest` (or no tag) means the running image can change without a change
record, which breaks reproducibility and change control.

# Satisfies

- [CC8.1 — Change Management](../controls/cc8.1.md)

# Enforced at

- Deploy gate: Conftest in CI, blocking
- Also detected by Checkov and Trivy (listed in `rule_ids`)

# Remediation

Pin every container image to a released version tag or an `@sha256:` digest,
and update it only through a reviewed change.
