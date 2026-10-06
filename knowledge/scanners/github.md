---
type: Scanner
title: GitHub collectors
description: Branch rules, CI scanner jobs and merged changes, read from the GitHub API.
resource: https://docs.github.com/en/rest
tags: [scm, change-management, cc8.1]
rule_ids:
  - "github:scm-*"
  - "github:change-*"
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-06T00:00:00+00:00"
verified:
  - by: "human:cdevarenne"
    at: "2026-10-06T11:53:00-07:00"
---
# Covers

Read-only collectors over the GitHub API (`grc collect`), with no clone of the
target repos:

- **SCM posture** (`scm-*`): on each repo's default branch, the required
  approving reviews, the required status checks, whether anyone can bypass the
  rules, and whether each configured scanner job is present and can fail the
  build. Rules the token cannot read give `scm-rules-unreadable`, never a pass.
- **Change population** (`change-*`): every change merged in the audit window,
  with a finding for a change with no independent approval
  (`change-no-approval`) and for one its author merged with no approval
  (`change-self-merge-without-review`).

A posture finding states the setting on the day it was read. The window report
uses only the evidence ledger for history.

# Evidences

- [CC8.1 — Change Management](../controls/cc8.1.md)
