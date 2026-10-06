---
type: Scanner Check
title: Pin images and modules to reviewed sources
description: Images are pinned by digest from trusted registries, admission requires attested images, and Terraform modules are pinned to a commit.
tags: [kubernetes, terraform, cc8.1]
rule_ids:
  - checkov:CKV_K8S_43
  - checkov:CKV_TF_1
  - checkov:CKV_GCP_66
  - trivy:KSV-0125
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-01T15:48:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-10-01T15:58:00-07:00"
---
# Rule

A tag or a branch can move after review. A digest, a commit, and an
allowlisted registry make what is deployed exactly what was reviewed;
Binary Authorization enforces it at admission.

# Satisfies

- [CC8.1 — Change Management](../controls/cc8.1.md)

# Enforced at

- Detected by Checkov and Trivy (listed in `rule_ids`); no rule of this bundle enforces it

# Remediation

Reference images as `image@sha256:…` from an allowlisted registry, pin each
Terraform module `source` to a commit (`?ref=<sha>`), and enable Binary
Authorization on the cluster.
