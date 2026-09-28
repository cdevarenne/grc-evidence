---
type: Semgrep Rule
title: Do not log prompts
tags: [semgrep, iso42001:a.7, eu-ai-act:art-12]
rule_ids: ["semgrep:llm-prompt-logged"]
---
# Remediation
Log a prompt hash, not the prompt.
