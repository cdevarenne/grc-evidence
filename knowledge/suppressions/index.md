# Suppressions

Reviewed, time-limited decisions about one exact finding each. A suppression
changes how a finding counts, never whether it is shown: every report lists
suppressed, expired, and unused suppressions.

* [Own registry flagged as untrusted](trivy-trusted-registry.md) - Trivy's default trusted-registry list does not include the project's own registry.
* [Django multiple-file upload bypass (CVE-2023-31047)](django-cve-2023-31047.md) - Accepted until the scheduled upgrade; the sample API has no file uploads.
