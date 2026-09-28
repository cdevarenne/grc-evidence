# Compliance Scan Report

Generated 2026-09-28T18:09:34+00:00. Every status below is derived from scanner findings joined to
controls declared in the OKF knowledge bundle; nothing is mapped without a declaration.
`no-violations-detected` means automated checks found nothing for that control;
it is evidence, not a control attestation.

## Risk posture

71 open findings across 8 of 12 controls: 3 critical, 26 high, 25 medium, 12 low, 5 unclassified.
0 controls show no violations. 4 not assessed. 6 not applicable. 42 coverage gaps to triage.

## Summary

| Control | Status | Critical | High | Medium | Low | Uncl. | Total |
|---|---|---|---|---|---|---|---|
| soc2:cc6.1 | not-satisfied | 0 | 4 | 1 | 1 | 2 | 8 |
| soc2:cc6.6 | not-satisfied | 0 | 2 | 0 | 0 | 2 | 4 |
| soc2:cc7.1 | not-satisfied | 3 | 16 | 21 | 11 | 0 | 51 |
| soc2:cc7.2 | not-assessed | 0 | 0 | 0 | 0 | 0 | 0 |
| soc2:cc8.1 | not-satisfied | 0 | 1 | 1 | 0 | 1 | 3 |
| iso42001:a.4 | not-satisfied | 0 | 1 | 0 | 0 | 0 | 1 |
| iso42001:a.5 | not-assessed | 0 | 0 | 0 | 0 | 0 | 0 |
| iso42001:a.6 | not-satisfied | 0 | 1 | 1 | 0 | 0 | 2 |
| iso42001:a.7 | not-satisfied | 0 | 1 | 0 | 0 | 0 | 1 |
| iso42001:a.8 | not-assessed | 0 | 0 | 0 | 0 | 0 | 0 |
| iso42001:a.9 | not-assessed | 0 | 0 | 0 | 0 | 0 | 0 |
| eu-ai-act:art-9 | not-applicable | 0 | 0 | 0 | 0 | 0 | 0 |
| eu-ai-act:art-10 | not-applicable | 0 | 0 | 0 | 0 | 0 | 0 |
| eu-ai-act:art-12 | not-applicable | 0 | 1 | 0 | 0 | 0 | 1 |
| eu-ai-act:art-13 | not-applicable | 0 | 0 | 0 | 0 | 0 | 0 |
| eu-ai-act:art-14 | not-applicable | 0 | 0 | 0 | 0 | 0 | 0 |
| eu-ai-act:art-15 | not-applicable | 0 | 0 | 0 | 0 | 0 | 0 |
| eu-ai-act:art-50 | not-satisfied | 0 | 0 | 1 | 0 | 0 | 1 |

## SOC 2

### CC6.1 — Logical Access

**Status:** not-satisfied

**Findings:** 4 high, 1 medium, 1 low, 2 unclassified

**Evidence:** [Checkov](../knowledge/scanners/checkov.md), [Conftest](../knowledge/scanners/conftest.md), [Semgrep](../knowledge/scanners/semgrep.md), [Trivy](../knowledge/scanners/trivy.md), [DRF writes require authentication](../knowledge/policies/drf-authenticated-writes.md), [No hard-coded LLM API keys](../knowledge/policies/llm-hardcoded-key.md), [Require non-root containers](../knowledge/policies/require-non-root.md)

**Open findings:**

- `semgrep` `llm-hardcoded-key` (high) — An API key is assigned from a string literal; read it from the environment or a secret store. — `app/assistant/settings.py`
- `semgrep` `drf-allowany` (high) — DRF view allows unauthenticated access (AllowAny); require an authenticated permission class. — `app/widgets/views.py`
- `trivy` `DS-0002` (high) — Image user should not be 'root': Specify at least 1 USER command in Dockerfile with non-root user as argument — `app/Dockerfile`
- `trivy` `KSV-0012` (medium) — Runs as root user: Container 'api' of Deployment 'widgets-api' should set 'securityContext.runAsNonRoot' to true — `app/k8s/deployment.yaml`
- `trivy` `KSV-0105` (low) — Containers must not set runAsUser to 0: securityContext.runAsUser should be set to a value greater than 0 — `app/k8s/deployment.yaml`
- `checkov` `CKV_DOCKER_3` (unknown) — Ensure that a user for the container has been created (/Dockerfile.) — `app/Dockerfile`
- `checkov` `CKV_K8S_23` (unknown) — Minimize the admission of root containers (Deployment.default.widgets-api) — `app/k8s/deployment.yaml`
- `conftest` `require_non_root` (high) — Deployment container "api" does not run as non-root (set runAsNonRoot: true) — `app/k8s/deployment.yaml`

**Remediation:** Read the key from the environment (for example `os.environ["ANTHROPIC_API_KEY"]`)
or a secret manager, and rotate any key that was committed. Replace `AllowAny` with an authenticated permission class (for example
`IsAuthenticated`, or `IsAuthenticatedOrReadOnly` for public reads). Add a non-root `USER` to the Dockerfile and set `securityContext.runAsNonRoot: true`
(with a non-zero `runAsUser`) on every container in the Deployment.

### CC6.6 — System Boundary Protection

**Status:** not-satisfied

**Findings:** 2 high, 2 unclassified

**Evidence:** [Checkov](../knowledge/scanners/checkov.md), [Conftest](../knowledge/scanners/conftest.md), [Trivy](../knowledge/scanners/trivy.md), [No public buckets](../knowledge/policies/no-public-bucket.md)

**Open findings:**

- `trivy` `GCP-0001` (high) — Ensure that Cloud Storage bucket is not anonymously or publicly accessible.: Bucket allows public access. — `app/infra/main.tf`
- `checkov` `CKV_GCP_114` (unknown) — Ensure public access prevention is enforced on Cloud Storage bucket (google_storage_bucket.widgets_assets) — `app/infra/main.tf`
- `checkov` `CKV_GCP_28` (unknown) — Ensure that Cloud Storage bucket is not anonymously or publicly accessible (google_storage_bucket_iam_member.public_read) — `app/infra/main.tf`
- `conftest` `no_public_bucket` (high) — bucket IAM binding "public_read" grants access to allUsers — `app/infra/main.tf`

**Remediation:** Remove public IAM members from the bucket, grant access to named service
accounts only, and enforce public access prevention on the bucket.

### CC7.1 — Vulnerability Detection

**Status:** not-satisfied

**Findings:** 3 critical, 16 high, 21 medium, 11 low

**Evidence:** [Trivy](../knowledge/scanners/trivy.md)

**Open findings:**

- `trivy` `CVE-2023-31047` (critical) — Django 4.2.0: python-django: Potential bypass of validation when uploading multiple files using one form field — `app/requirements.txt`
- `trivy` `CVE-2024-42005` (critical) — Django 4.2.0: python-django: Potential SQL injection in QuerySet.values() and values_list() — `app/requirements.txt`
- `trivy` `CVE-2025-64459` (critical) — Django 4.2.0: django: Django SQL injection — `app/requirements.txt`
- `trivy` `CVE-2023-36053` (high) — Django 4.2.0: python-django: Potential regular expression denial of service vulnerability in EmailValidator/URLValidator — `app/requirements.txt`
- `trivy` `CVE-2023-43665` (high) — Django 4.2.0: python-django: Denial-of-service possibility in django.utils.text.Truncator — `app/requirements.txt`
- `trivy` `CVE-2023-46695` (high) — Django 4.2.0: python-django: Potential denial of service vulnerability in UsernameField on Windows — `app/requirements.txt`
- `trivy` `CVE-2024-24680` (high) — Django 4.2.0: Django: denial-of-service in ``intcomma`` template filter — `app/requirements.txt`
- `trivy` `CVE-2024-38875` (high) — Django 4.2.0: python-django: Potential denial-of-service in django.utils.html.urlize() — `app/requirements.txt`
- `trivy` `CVE-2024-39330` (high) — Django 4.2.0: python-django: Potential directory-traversal in django.core.files.storage.Storage.save() — `app/requirements.txt`
- `trivy` `CVE-2024-39614` (high) — Django 4.2.0: python-django: Potential denial-of-service in django.utils.translation.get_supported_language_variant() — `app/requirements.txt`
- `trivy` `CVE-2024-53908` (high) — Django 4.2.0: django: Potential SQL injection in HasKey(lhs, rhs) on Oracle — `app/requirements.txt`
- `trivy` `CVE-2025-57833` (high) — Django 4.2.0: django: Django SQL injection in FilteredRelation column aliases — `app/requirements.txt`
- `trivy` `CVE-2025-59681` (high) — Django 4.2.0: django: Potential SQL injection in QuerySet.annotate(), alias(), aggregate(), and extra() on MySQL and MariaDB1 — `app/requirements.txt`
- `trivy` `CVE-2025-64458` (high) — Django 4.2.0: Django: Denial-of-service vulnerability in Django on Windows — `app/requirements.txt`
- `trivy` `CVE-2026-1207` (high) — Django 4.2.0: Django: Django: SQL Injection via RasterField band index parameter — `app/requirements.txt`
- `trivy` `CVE-2026-1287` (high) — Django 4.2.0: Django: Django: SQL Injection via crafted column aliases — `app/requirements.txt`
- `trivy` `CVE-2026-25673` (high) — Django 4.2.0: django: Django: Denial of Service via slow URL normalization on Windows — `app/requirements.txt`
- `trivy` `CVE-2026-33034` (high) — Django 4.2.0: Django: Django: Denial of Service via missing or understated Content-Length header in ASGI requests — `app/requirements.txt`
- `trivy` `CVE-2026-3902` (high) — Django 4.2.0: Django: Django: Header spoofing via ambiguous header mapping — `app/requirements.txt`
- `trivy` `CVE-2023-41164` (medium) — Django 4.2.0: python-django: Potential denial of service vulnerability in  ``django.utils.encoding.uri_to_iri()`` — `app/requirements.txt`
- `trivy` `CVE-2024-27351` (medium) — Django 4.2.0: python-django: Potential regular expression denial-of-service in django.utils.text.Truncator.words() — `app/requirements.txt`
- `trivy` `CVE-2024-39329` (medium) — Django 4.2.0: python-django: Username enumeration through timing difference for users with unusable passwords — `app/requirements.txt`
- `trivy` `CVE-2024-41989` (medium) — Django 4.2.0: python-django: Memory exhaustion in django.utils.numberformat.floatformat() — `app/requirements.txt`
- `trivy` `CVE-2024-41990` (medium) — Django 4.2.0: python-django: Potential denial-of-service vulnerability in django.utils.html.urlize() — `app/requirements.txt`
- `trivy` `CVE-2024-41991` (medium) — Django 4.2.0: python-django: Potential denial-of-service vulnerability in django.utils.html.urlize() and AdminURLFieldWidget — `app/requirements.txt`
- `trivy` `CVE-2024-45230` (medium) — Django 4.2.0: python-django: Potential denial-of-service vulnerability in django.utils.html.urlize() — `app/requirements.txt`
- `trivy` `CVE-2024-45231` (medium) — Django 4.2.0: python-django: Potential user email enumeration via response status on password reset — `app/requirements.txt`
- `trivy` `CVE-2024-53907` (medium) — Django 4.2.0: django: Potential denial-of-service in django.utils.html.strip_tags() — `app/requirements.txt`
- `trivy` `CVE-2024-56374` (medium) — Django 4.2.0: django: potential denial-of-service vulnerability in IPv6 validation — `app/requirements.txt`
- `trivy` `CVE-2025-13372` (medium) — Django 4.2.0: django: Django: SQL injection in FilteredRelation column aliases — `app/requirements.txt`
- `trivy` `CVE-2025-26699` (medium) — Django 4.2.0: django: Potential denial-of-service vulnerability in django.utils.text.wrap() — `app/requirements.txt`
- `trivy` `CVE-2025-32873` (medium) — Django 4.2.0: django: Django StripTags Denial of Service — `app/requirements.txt`
- `trivy` `CVE-2025-48432` (medium) — Django 4.2.0: django: Django Path Injection Vulnerability — `app/requirements.txt`
- `trivy` `CVE-2025-64460` (medium) — Django 4.2.0: Django: Django: Algorithmic complexity in XML Deserializer leads to denial of service — `app/requirements.txt`
- `trivy` `CVE-2026-1312` (medium) — Django 4.2.0: Django: Django: SQL injection via crafted column aliases in QuerySet.order_by() — `app/requirements.txt`
- `trivy` `CVE-2026-33033` (medium) — Django 4.2.0: Django: Django: Performance degradation via excessive whitespace in multipart uploads — `app/requirements.txt`
- `trivy` `CVE-2026-53877` (medium) — Django 4.2.0: django: Django: Information disclosure via heap buffer over-read in GDALRaster — `app/requirements.txt`
- `trivy` `CVE-2026-53878` (medium) — Django 4.2.0: django: Django: HTTP header injection via DomainNameValidator accepting newlines — `app/requirements.txt`
- `trivy` `CVE-2025-13473` (low) — Django 4.2.0: Django: Django: User enumeration via timing attack in mod_wsgi authentication — `app/requirements.txt`
- `trivy` `CVE-2025-14550` (low) — Django 4.2.0: Django: Django: Denial of Service via crafted request with duplicate headers — `app/requirements.txt`
- `trivy` `CVE-2025-59682` (low) — Django 4.2.0: django: Potential partial directory-traversal via archive.extract() — `app/requirements.txt`
- `trivy` `CVE-2026-1285` (low) — Django 4.2.0: Django: Django: Denial of Service via crafted HTML inputs — `app/requirements.txt`
- `trivy` `CVE-2026-25674` (low) — Django 4.2.0: django: Django: Incorrect file permissions due to race condition — `app/requirements.txt`
- `trivy` `CVE-2026-4277` (low) — Django 4.2.0: Django: Django: Privilege Abuse via Forged POST Data in GenericInlineModelAdmin — `app/requirements.txt`
- `trivy` `CVE-2026-4292` (low) — Django 4.2.0: Django: Django: Unauthorized instance creation via forged POST data in Admin changelist forms — `app/requirements.txt`
- `trivy` `CVE-2026-48587` (low) — Django 4.2.0: django: Django: Information disclosure via improper handling of Vary header whitespace — `app/requirements.txt`
- `trivy` `CVE-2026-48588` (low) — Django 4.2.0: django: Django: Information disclosure due to improper caching of Set-Cookie responses — `app/requirements.txt`
- `trivy` `CVE-2026-6873` (low) — Django 4.2.0: python-django: Django: Information disclosure via non-injective cookie salt derivation — `app/requirements.txt`
- `trivy` `CVE-2026-8404` (low) — Django 4.2.0: Django: Django: Information disclosure due to improper handling of Cache-Control directives — `app/requirements.txt`
- `trivy` `CVE-2026-73228` (medium) — djangorestframework 3.15.2: djangorestframework: Django REST framework: Denial of Service via oversized request bodies — `app/requirements.txt`
- `trivy` `CVE-2026-73229` (medium) — djangorestframework 3.15.2: djangorestframework: Django REST framework: Information disclosure via improper permission checks in AdminRenderer — `app/requirements.txt`

**Remediation:** Upgrade each vulnerable dependency to a version that fixes the listed
advisories, then re-scan.

### CC8.1 — Change Management

**Status:** not-satisfied

**Findings:** 1 high, 1 medium, 1 unclassified

**Evidence:** [Checkov](../knowledge/scanners/checkov.md), [Conftest](../knowledge/scanners/conftest.md), [Trivy](../knowledge/scanners/trivy.md), [Deny :latest image tag](../knowledge/policies/deny-latest-tag.md)

**Open findings:**

- `trivy` `KSV-0013` (medium) — Image tag ":latest" used: Container 'api' of Deployment 'widgets-api' should specify an image tag — `app/k8s/deployment.yaml`
- `checkov` `CKV_K8S_14` (unknown) — Image Tag should be fixed - not latest or blank (Deployment.default.widgets-api) — `app/k8s/deployment.yaml`
- `conftest` `deny_latest_tag` (high) — Deployment container "api" uses unpinned image "ghcr.io/example/widgets-api:latest" — `app/k8s/deployment.yaml`

**Remediation:** Pin every container image to a released version tag or an `@sha256:` digest,
and update it only through a reviewed change.

## ISO/IEC 42001

### A.4 — Resources for AI systems

**Status:** not-satisfied

**Findings:** 1 high

**Evidence:** [Conftest](../knowledge/scanners/conftest.md), [AI inventory is complete](../knowledge/policies/ai-inventory-complete.md)

**Open findings:**

- `conftest` `ai_inventory_complete` (high) — AI component "app/assistant" has no entry in the AI system inventory — `app/ai-inventory.yaml`

**Remediation:** Add a `systems` entry for the component with its owner, model provider, and
purpose, then review its risk tier.

### A.6 — AI system life cycle

**Status:** not-satisfied

**Findings:** 1 high, 1 medium

**Evidence:** [Semgrep](../knowledge/scanners/semgrep.md), [No hard-coded LLM API keys](../knowledge/policies/llm-hardcoded-key.md), [Bound every LLM call](../knowledge/policies/llm-unbounded-call.md)

**Open findings:**

- `semgrep` `llm-hardcoded-key` (high) — An API key is assigned from a string literal; read it from the environment or a secret store. — `app/assistant/settings.py`
- `semgrep` `llm-unbounded-call` (medium) — LLM call without both a timeout and a max_tokens bound; set both. — `app/assistant/views.py`

**Remediation:** Read the key from the environment (for example `os.environ["ANTHROPIC_API_KEY"]`)
or a secret manager, and rotate any key that was committed. Pass `timeout=` and `max_tokens=` on every `messages.create` call, sized to the
feature's latency and cost budget.

### A.7 — Data for AI systems

**Status:** not-satisfied

**Findings:** 1 high

**Evidence:** [Semgrep](../knowledge/scanners/semgrep.md), [Do not log prompts or completions](../knowledge/policies/llm-prompt-logged.md)

**Open findings:**

- `semgrep` `llm-prompt-logged` (high) — A prompt or model completion is written to the log in clear text; log a hash or an id instead. — `app/assistant/views.py`

**Remediation:** Log a request id and a hash of the prompt, not the prompt or the completion.
Keep full transcripts, if needed, in a store with its own access control and retention.

## EU AI Act

### Art. 50 — Transparency obligations for certain AI systems

**Status:** not-satisfied

**Findings:** 1 medium

**Evidence:** [Semgrep](../knowledge/scanners/semgrep.md), [Disclose AI-generated output](../knowledge/policies/llm-no-ai-disclosure.md)

**Open findings:**

- `semgrep` `llm-no-ai-disclosure` (medium) — A view returns model output without telling the user it is AI-generated; add an ai_generated field. — `app/assistant/views.py`

**Remediation:** Add `"ai_generated": true` to every response that carries model output, and
show it in the client.

## Crosswalk

Links between frameworks. A link is navigation, never a mapping: each status
comes only from that control's own rule declarations.

| Control | Status | Linked control | Status | Source |
|---|---|---|---|---|
| iso42001:a.5 | not-assessed | eu-ai-act:art-9 | not-applicable | [ISO/IEC 42001 ↔ EU AI Act](../knowledge/crosswalk/iso42001-ai-act.md) |
| iso42001:a.7 | not-satisfied | eu-ai-act:art-10 | not-applicable | [ISO/IEC 42001 ↔ EU AI Act](../knowledge/crosswalk/iso42001-ai-act.md) |
| iso42001:a.7 | not-satisfied | eu-ai-act:art-12 | not-applicable | [ISO/IEC 42001 ↔ EU AI Act](../knowledge/crosswalk/iso42001-ai-act.md) |
| iso42001:a.8 | not-assessed | eu-ai-act:art-13 | not-applicable | [ISO/IEC 42001 ↔ EU AI Act](../knowledge/crosswalk/iso42001-ai-act.md) |
| iso42001:a.8 | not-assessed | eu-ai-act:art-50 | not-satisfied | [ISO/IEC 42001 ↔ EU AI Act](../knowledge/crosswalk/iso42001-ai-act.md) |
| iso42001:a.9 | not-assessed | eu-ai-act:art-14 | not-applicable | [ISO/IEC 42001 ↔ EU AI Act](../knowledge/crosswalk/iso42001-ai-act.md) |
| iso42001:a.6 | not-satisfied | eu-ai-act:art-15 | not-applicable | [ISO/IEC 42001 ↔ EU AI Act](../knowledge/crosswalk/iso42001-ai-act.md) |
| soc2:cc6.1 | not-satisfied | iso42001:a.6 | not-satisfied | [SOC 2 ↔ ISO/IEC 42001](../knowledge/crosswalk/soc2-iso42001.md) |
| soc2:cc7.2 | not-assessed | iso42001:a.6 | not-satisfied | [SOC 2 ↔ ISO/IEC 42001](../knowledge/crosswalk/soc2-iso42001.md) |
| soc2:cc8.1 | not-satisfied | iso42001:a.6 | not-satisfied | [SOC 2 ↔ ISO/IEC 42001](../knowledge/crosswalk/soc2-iso42001.md) |

## Coverage gaps

Findings with no in-bundle control. These are gaps to close, not mappings to invent.

- `semgrep` `llm-output-unreviewed-write` (medium) — Model output is written to a record with no human-review flag checked first. — `app/assistant/views.py` — reason: `no-rule-match`
- `trivy` `DS-0026` (low) — No HEALTHCHECK defined: Add HEALTHCHECK instruction in your Dockerfile — `app/Dockerfile` — reason: `no-rule-match`
- `trivy` `GCP-0066` (low) — Cloud Storage buckets should be encrypted with a customer-managed key.: Storage bucket encryption does not use a customer-managed key. — `app/infra/main.tf` — reason: `no-rule-match`
- `trivy` `GCP-0077` (medium) — Cloud Storage Bucket Logging Not Enabled: Storage bucket logging is not configured with a target log bucket. — `app/infra/main.tf` — reason: `no-rule-match`
- `trivy` `GCP-0078` (medium) — Cloud Storage Bucket Versioning Disabled: Storage bucket versioning is not enabled. — `app/infra/main.tf` — reason: `no-rule-match`
- `trivy` `KSV-0001` (medium) — Can elevate its own privileges: Container 'api' of Deployment 'widgets-api' should set 'securityContext.allowPrivilegeEscalation' to false — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0003` (low) — Default capabilities: some containers do not drop all: Container 'api' of Deployment 'widgets-api' should add 'ALL' to 'securityContext.capabilities.drop' — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0004` (low) — Default capabilities: some containers do not drop any: Container 'api' of 'deployment' 'widgets-api' in 'default' namespace should set securityContext.capabilities.drop — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0011` (low) — CPU not limited: Container 'api' of Deployment 'widgets-api' should set 'resources.limits.cpu' — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0014` (high) — Root file system is not read-only: Container 'api' of Deployment 'widgets-api' should set 'securityContext.readOnlyRootFilesystem' to true — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0015` (low) — CPU requests not specified: Container 'api' of Deployment 'widgets-api' should set 'resources.requests.cpu' — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0016` (low) — Memory requests not specified: Container 'api' of Deployment 'widgets-api' should set 'resources.requests.memory' — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0018` (low) — Memory not limited: Container 'api' of Deployment 'widgets-api' should set 'resources.limits.memory' — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0020` (low) — Runs with UID <= 10000: Container 'api' of Deployment 'widgets-api' should set 'securityContext.runAsUser' > 10000 — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0021` (low) — Runs with GID <= 10000: Container 'api' of Deployment 'widgets-api' should set 'securityContext.runAsGroup' > 10000 — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0030` (low) — Runtime/Default Seccomp profile not set: Either Pod or Container should set 'securityContext.seccompProfile.type' to 'RuntimeDefault' — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0104` (medium) — Seccomp policies disabled: container "api" of deployment "widgets-api" in "default" namespace should specify a seccomp profile — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0106` (low) — Container capabilities must only include NET_BIND_SERVICE: container should drop all — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0110` (low) — Workloads in the default namespace: deployment widgets-api in default namespace should set metadata.namespace to a non-default namespace — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0118` (high) — Default security context configured: deployment widgets-api in default namespace is using the default security context, which allows root privileges — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `trivy` `KSV-0125` (medium) — Restrict container images to trusted registries: Container api in deployment widgets-api (namespace: default) uses an image from an untrusted registry. — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_DOCKER_2` (unknown) — Ensure that HEALTHCHECK instructions have been added to container images (/Dockerfile.) — `app/Dockerfile` — reason: `no-rule-match`
- `checkov` `CKV_K8S_12` (unknown) — Memory requests should be set (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_9` (unknown) — Readiness Probe Should be Configured (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_10` (unknown) — CPU requests should be set (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_11` (unknown) — CPU limits should be set (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_43` (unknown) — Image should use digest (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_37` (unknown) — Minimize the admission of containers with capabilities assigned (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_28` (unknown) — Minimize the admission of containers with the NET_RAW capability (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_38` (unknown) — Ensure that Service Account Tokens are only mounted where necessary (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_40` (unknown) — Containers should run as a high UID to avoid host conflict (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_29` (unknown) — Apply security context to your pods and containers (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_20` (unknown) — Containers should not run with allowPrivilegeEscalation (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_21` (unknown) — The default namespace should not be used (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_13` (unknown) — Memory limits should be set (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_22` (unknown) — Use read-only filesystem for containers where possible (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_8` (unknown) — Liveness Probe Should be Configured (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_31` (unknown) — Ensure that the seccomp profile is set to docker/default or runtime/default (Deployment.default.widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_K8S_21` (unknown) — The default namespace should not be used (Service.default.widgets-api) — `app/k8s/service.yaml` — reason: `no-rule-match`
- `checkov` `CKV2_K8S_6` (unknown) — Minimize the admission of pods which lack an associated NetworkPolicy (Pod.default.widgets-api.app-widgets-api) — `app/k8s/deployment.yaml` — reason: `no-rule-match`
- `checkov` `CKV_GCP_62` (unknown) — Bucket should log access (google_storage_bucket.widgets_assets) — `app/infra/main.tf` — reason: `no-rule-match`
- `checkov` `CKV_GCP_78` (unknown) — Ensure Cloud storage has versioning enabled (google_storage_bucket.widgets_assets) — `app/infra/main.tf` — reason: `no-rule-match`

## Not assessed

- CC7.2 — Security Monitoring: no in-bundle scanner or policy evidences this control.
- A.5 — Assessing impacts of AI systems: no in-bundle scanner or policy evidences this control.
- A.8 — Information for interested parties of AI systems: no in-bundle scanner or policy evidences this control.
- A.9 — Use of AI systems: no in-bundle scanner or policy evidences this control.

## Not applicable

Out of scope at the declared AI risk tier. Findings stay listed; they do not change the status.

- Art. 9 — Risk management system
- Art. 10 — Data and data governance
- Art. 12 — Record-keeping
  - `semgrep` `llm-prompt-logged` (high) — A prompt or model completion is written to the log in clear text; log a hash or an id instead. — `app/assistant/views.py`
- Art. 13 — Transparency and provision of information to deployers
- Art. 14 — Human oversight
- Art. 15 — Accuracy, robustness and cybersecurity
