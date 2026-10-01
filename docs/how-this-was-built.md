# How this was built

The process behind the code: specs, plans, human gates, and measurements.

Built with an AI coding agent under a written process; the record is in the repo.

- **Spec, then plan, then tasks.** Each change starts as a spec in
  [`docs/superpowers/specs/`](superpowers/specs/), becomes a step-by-step
  plan in [`docs/superpowers/plans/`](superpowers/plans/) with complete
  code and expected outputs, and is executed task by task: failing test first,
  then the code, then one commit per task with a tracking issue.
- **Plans are prototyped before they are written down.** Plan code was run
  against the pinned scanners first. Executing the plans verbatim still caught
  four plan bugs (two malformed diffs, a duplicated hunk, a case-sensitive
  assertion), fixed in the plans as well as the code.
- **Human gates where judgment is needed.** New knowledge concepts carry a
  `verified` entry only after a person reviews them (the conformance test fails
  until then); ISO/IEC 42001 clause ids were checked against a licensed copy;
  every eval label set was reviewed before its first run.
- **Measure, don't assume.** The triage prompt was changed only in response to
  a measured failure, on a split that did not inform the fix, with the decision
  rule posted to the issue before the deciding run
  ([#32](https://github.com/cdevarenne/okf-grc-skill/issues/32)). A fix that
  improved the diagnosis set but not the held-out set was recorded as such.
- **The tool is held to its own rules.** The AI-governance Semgrep rules flagged
  this repo's own LLM client (no request timeout); the client was fixed, not
  the rule.
- **Bugs found by the process, not by users:** gap rules sent without the id
  the model had to echo (every first proposal invalid); batch ids the API
  rejects; a batch budget check that looked at one request at a time; a silent
  wait on long batches. Each fix came with a test that fails on the old code.
- **Costs are measured.** Every model call is logged with tokens and cost; the
  README's figures come from that log, not estimates.
