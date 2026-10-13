---
type: Scanner Check
title: Log access to storage buckets
description: Each Cloud Storage bucket writes access logs to a log bucket.
tags: [terraform, gcs, cc7.2]
rule_ids:
  - checkov:CKV_GCP_62
  - trivy:GCP-0077
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-12T17:16:00-07:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-10-12T17:45:00-07:00"
---
# Rule

Access logs record who read or changed which object, and when. Without them, a
bucket that is misused or exfiltrated leaves nothing to detect it with or to
investigate afterwards.

# Satisfies

- [CC7.2 — Security Monitoring](../controls/cc7.2.md)

# Enforced at

- Detected by Checkov and Trivy (listed in `rule_ids`); no rule of this bundle enforces it

# Remediation

Give each `google_storage_bucket` a `logging` block whose `log_bucket` is a
separate bucket that only the logging service and security reviewers can
write to and read.
