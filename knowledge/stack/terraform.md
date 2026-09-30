---
type: Stack Component
title: Terraform module
description: Storage bucket and service account for the API.
resource: ../../app/infra/main.tf
tags: [terraform, iac, gcp]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-25T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-29T17:21:00-07:00"
---
# What it is

A generic storage bucket, an IAM binding on it, and a service account.

# Controls that apply

- [CC6.6 — System Boundary Protection](../controls/cc6.6.md)

# Scanned by

- [Checkov](../scanners/checkov.md)
- [Trivy](../scanners/trivy.md)
- [Conftest](../scanners/conftest.md)
