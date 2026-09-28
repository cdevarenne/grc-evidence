# Compliance Scan Report

Generated 2026-09-25T12:00:00+00:00. Every status below is derived from scanner findings joined to
controls declared in the OKF knowledge bundle; nothing is mapped without a declaration.
`no-violations-detected` means automated checks found nothing for that control;
it is evidence, not a control attestation.

## Risk posture

3 open findings across 2 of 4 controls: 1 critical, 1 high, 1 medium.
1 control shows no violations. 1 not assessed. 2 coverage gaps to triage.

## Summary

| Control | Status | Critical | High | Medium | Low | Uncl. | Total |
|---|---|---|---|---|---|---|---|
| soc2:cc6.1 | not-satisfied | 0 | 1 | 1 | 0 | 0 | 2 |
| soc2:cc7.1 | not-satisfied | 1 | 0 | 0 | 0 | 0 | 1 |
| soc2:cc7.2 | not-assessed | 0 | 0 | 0 | 0 | 0 | 0 |
| soc2:cc8.1 | no-violations-detected | 0 | 0 | 0 | 0 | 0 | 0 |

## SOC 2

### CC6.1 — Logical Access

**Status:** not-satisfied

**Findings:** 1 high, 1 medium

**Evidence:** [Require non-root](../knowledge/policies/require-non-root.md)

**Open findings:**

- `conftest` `require_non_root` (high) — container runs as root — `app/k8s/deployment.yaml`
- `checkov` `CKV_TEST_1` (medium) — runAsNonRoot not set — `app/k8s/deployment.yaml`

**Remediation:** Run the container as a non-root user.

### CC7.1 — Vulnerability Detection

**Status:** not-satisfied

**Findings:** 1 critical

**Evidence:** [Trivy](../knowledge/scanners/trivy.md)

**Open findings:**

- `trivy` `CVE-2024-0001` (critical) — example-pkg 1.0 vulnerable — `app/requirements.txt`

**Remediation:** Upgrade the affected dependency to a fixed version.

### CC8.1 — Change Management

**Status:** no-violations-detected

**Evidence:** [Deny latest tag](../knowledge/policies/deny-latest-tag.md)

## Coverage gaps

Findings with no in-bundle control. These are gaps to close, not mappings to invent.

- `checkov` `CKV_TEST_99` (low) — no HEALTHCHECK — `app/Dockerfile` — reason: `no-rule-match`
- `conftest` `orphan_rule` (medium) — orphan — `app/infra/main.tf` — reason: `control-not-in-bundle`

## Not assessed

- CC7.2 — Monitoring: no in-bundle scanner or policy evidences this control.
