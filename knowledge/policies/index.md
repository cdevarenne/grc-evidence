# Policies

Each guardrail declares, in `rule_ids`, every scanner rule that detects a
violation of it. A concept that declares `rule_ids` carries exactly one
control tag per framework.

* [Require non-root containers](require-non-root.md) - Containers and images must not run as root.
* [Deny :latest image tag](deny-latest-tag.md) - Deployments and Dockerfile base images must pin an immutable image tag or digest.
* [No public buckets](no-public-bucket.md) - Storage buckets must not grant access to allUsers or allAuthenticatedUsers.
* [Do not log prompts or completions](llm-prompt-logged.md) - Prompts and model outputs must not be written to application logs in clear text.
* [No hard-coded LLM API keys](llm-hardcoded-key.md) - Model-provider API keys must come from the environment or a secret store.
* [Bound every LLM call](llm-unbounded-call.md) - Every model call sets both a timeout and a max_tokens limit.
* [Disclose AI-generated output](llm-no-ai-disclosure.md) - Responses that carry model output tell the user it is AI-generated.
* [Harden the container runtime](harden-container-runtime.md) - Containers run with a seccomp profile, a read-only root file system, no mounted service-account token they do not need, and a high non-root UID and GID.
* [Isolate workloads in their own namespace](isolate-workloads.md) - Workloads do not run in the default namespace.
* [Pin images and modules to reviewed sources](pin-image-provenance.md) - Images are pinned by digest from trusted registries, admission requires attested images, and Terraform modules are pinned to a commit.
* [Keep the GKE cluster private](private-gke-control-plane.md) - The cluster's nodes and control plane are private, the API is reachable only from authorized networks, and network policy is enforced.
* [Least-privilege access to GKE](gke-access.md) - Cluster access uses Google identities and groups, not client certificates; nodes use a dedicated service account and the GKE metadata server.
* [Log network flows](network-flow-logs.md) - The cluster's VPC flow logs and intranode visibility are enabled.
* [Set resource requests and limits](set-resource-limits.md) - Every container declares CPU and memory requests and limits.
* [Declare health checks](health-checks.md) - Containers declare liveness and readiness probes, and images a HEALTHCHECK.
* [AI inventory is complete](ai-inventory-complete.md) - Every AI component of the app has an entry in the AI system inventory.
* [DRF writes require authentication](drf-authenticated-writes.md) - API views must not use AllowAny.
