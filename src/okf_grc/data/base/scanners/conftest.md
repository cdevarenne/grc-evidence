---
type: Scanner
title: Conftest
description: Runs the Rego guardrails as a deploy gate.
resource: https://github.com/open-policy-agent/conftest
tags: [opa, policy, cc8.1]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-25T14:50:00-07:00"
---
# Covers

Evaluates `policies/rego/` against the Kubernetes manifests and Terraform.
Each Rego package name is the rule id.

# Evidences

- [CC8.1 — Change Management](../controls/cc8.1.md)

# Rules

- [Require non-root containers](../policies/require-non-root.md)
- [Deny :latest image tag](../policies/deny-latest-tag.md)
- [No public buckets](../policies/no-public-bucket.md)
