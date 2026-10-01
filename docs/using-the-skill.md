# Using the skill

How to use the `grc-continuous-compliance` skill from a coding agent in this repo. The skill calls the same `grc` pipeline you can run yourself (see the [README](../README.md)).

The skill is a standard `SKILL.md` in 
`.claude/skills/grc-continuous-compliance/`, where Claude Code finds it automatically. 
Other coding agents that support skills can use the same file from their own skills location.
Ask for what you want, or name it with `/grc-continuous-compliance`. 
The pipeline itself needs no agent: see the `make` targets below.

Run `make bootstrap` once first (the skill runs it too if the scanners are missing).

Things to ask:

- "Review the compliance posture of the sample app."
- "Which controls are not satisfied, and what are the highest-severity findings?"
- "Which findings have no control? Propose mappings for them."
- "Summarize the AI-governance findings for an auditor."
- "This finding is a false positive: draft a suppression."

**What it does.** It runs `grc run` (here, `make scan`), reads the report and the mapping, and
summarizes the controls not satisfied, the highest-severity findings, the
coverage gaps, the controls not assessed or not applicable, and the state of the
suppressions. It can add LLM prose per control (`grc narrate`) and propose
controls for coverage gaps (`grc triage`).

**What it leaves to a reviewer/auditor.** It never changes a status, a count, or a
finding, and it never applies its own mapping proposals: a person adds
`rule_ids`. It drafts suppressions for review but does not add, renew, or extend
one, or edit `knowledge/`, unless asked. Text from scanned files is data to it,
never instructions.

It scans the layout `grc.yaml` describes; in this repo that is the default, `app/`. The `make` targets below run the same
pipeline without an agent.
