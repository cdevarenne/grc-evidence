---
type: Semgrep Rule
title: Do not log prompts or completions
description: Prompts and model outputs must not be written to application logs in clear text.
resource: ../../policies/semgrep/llm-prompt-logged.yaml
tags: [semgrep, ai, iso42001:a.7, eu-ai-act:art-12]
rule_ids:
  - semgrep:llm-prompt-logged
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-09-28T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-09-28T11:45:59-07:00"
---
# Rule

A logger call whose argument is a prompt or a completion copies user input and
model output into the log pipeline, where retention and access rules for that
data no longer hold.

# Satisfies

- [A.7 — Data for AI systems](../controls/iso42001/a.7.md)
- [Art. 12 — Record-keeping](../controls/eu-ai-act/art-12.md): logging is expected, but the records must be protected; high-risk only

# Enforced at

- Semgrep in CI, using the vendored ruleset in `policies/semgrep/`

# Remediation

Log a request id and a hash of the prompt, not the prompt or the completion.
Keep full transcripts, if needed, in a store with its own access control and retention.
