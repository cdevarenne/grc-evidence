---
type: Suppression
title: Own registry flagged as untrusted
description: Trivy's default trusted-registry list does not include the project's own registry.
kind: false-positive
finding:
  tool: trivy
  rule_id: KSV-0125
  target: app/k8s/deployment.yaml
  message_contains: "Container api in deployment widgets-api"
owner: human:cdevarenne
approved: "2026-09-28"
expires: "2026-12-27"
tags: [suppression, kubernetes]
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-28T16:18:36-07:00"
---
# Reason

The deployment pulls `ghcr.io/example/widgets-api`, the project's own registry.
Trivy judges KSV-0125 against its built-in list of trusted registries, which
does not include it, so the finding says nothing about this image's provenance.

# Renewal

Remove this suppression once the scan passes the project's registry to Trivy as
trusted; until then, renew it only after re-checking the image source.
