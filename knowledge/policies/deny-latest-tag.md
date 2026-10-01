---
type: Rego Policy
title: Deny :latest image tag
description: Deployments and Dockerfile base images must pin an immutable image tag or digest.
resource: ../../policies/rego/deny_latest_tag.rego
tags: [opa, conftest, kubernetes, docker, cc8.1]
rule_ids:
  - conftest:deny_latest_tag
  - checkov:CKV_K8S_14
  - checkov:CKV_DOCKER_7
  - trivy:KSV-0013
  - trivy:DS-0001
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
  - by: "human:cdevarenne"
    at: "2026-10-01T15:58:00-07:00"
---
# Rule

`:latest` (or no tag) means the running image can change without a change
record, which breaks reproducibility and change control.

# Satisfies

- [CC8.1 — Change Management](../controls/cc8.1.md)

# Enforced at

- Deploy gate: Conftest in CI, blocking
- Also detected by Checkov and Trivy (listed in `rule_ids`), which also check a Dockerfile's `FROM`

# Remediation

Pin every container image, including each Dockerfile's `FROM`, to a released version tag or an `@sha256:` digest,
and update it only through a reviewed change.
