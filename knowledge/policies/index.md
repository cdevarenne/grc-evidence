# Policies

Each guardrail declares, in `rule_ids`, every scanner rule that detects a
violation of it. A concept that declares `rule_ids` carries exactly one
control tag per framework.

* [Require non-root containers](require-non-root.md) - Containers and images must not run as root.
* [Deny :latest image tag](deny-latest-tag.md) - Deployments must pin an immutable image tag or digest.
* [No public buckets](no-public-bucket.md) - Storage buckets must not grant access to allUsers or allAuthenticatedUsers.
* [DRF writes require authentication](drf-authenticated-writes.md) - API views must not use AllowAny.
* [Do not log prompts or completions](llm-prompt-logged.md) - Prompts and model outputs must not be written to application logs in clear text.
* [No hard-coded LLM API keys](llm-hardcoded-key.md) - Model-provider API keys must come from the environment or a secret store.
* [Bound every LLM call](llm-unbounded-call.md) - Every model call sets both a timeout and a max_tokens limit.
* [Disclose AI-generated output](llm-no-ai-disclosure.md) - Responses that carry model output tell the user it is AI-generated.
* [AI inventory is complete](ai-inventory-complete.md) - Every AI component of the app has an entry in the AI system inventory.
