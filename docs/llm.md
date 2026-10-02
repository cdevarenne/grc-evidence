# LLM step and cost

The optional Claude API step: what it adds, how it is validated, what it costs, and how triage was evaluated.

The scan, the mapping, OSCAL, and every number in the report are deterministic.
An optional Claude API step adds words and proposals on top, never statuses:

- **`make narrate`** asks Claude for a one-sentence summary and auditor note per
  control. The whole answer is rejected, and the report keeps its own prose, if
  it names a status other than the control's own, calls anything satisfied,
  compliant, or passed, or uses a number that is not in the input.
- **`make triage`** proposes an in-bundle control, or `none`, for each coverage
  gap, in `out/proposals.json`. Nothing is applied: a person adds `rule_ids`.
  Default: Haiku 4.5, each control's framework scope and each gap's files in the
  input, and `low` and `medium` confidence proposals turned into `none` (the
  model's guess is kept in `cutoff_from`), chosen by the measurements below.
  `make triage TRIAGE_ARGS=--batch` sends it as one Message Batch instead:
  half price, results in minutes rather than seconds.
- **`make eval-triage`** scores triage on 57 labeled gaps (accuracy, and
  precision and recall of `none`) through the Message Batches API. Cases are
  split into `tune` (seen while diagnosing a problem), `holdout`, and
  `confirm` (each labeled before its first run), and each input variant
  (`baseline`, `scoped`) runs on all three; confidence cutoffs are chosen on
  `tune` only. The results below were measured on 65 cases against base
  1.2.0; base 1.2.1 maps 13 of those rules, so they are no longer gaps
  and were retired, and five reviewer-labeled cases were added. The first
  baseline is in
  [`examples/triage-eval-baseline.json`](../examples/triage-eval-baseline.json).

`LLM_MODE` picks the provider: `replay` (default; recorded responses, $0, used
by tests and CI), `record`, `anthropic` (the Claude API, key from the
environment), or `claude-cli` (Claude Code headless on your plan; dev loop
only, and not "the Claude API"). Defaults: `LLM_MODEL=claude-haiku-4-5`,
`LLM_BUDGET_USD=1`. Agent workflows (`grc agent`) use the same `LLM_MODE` and
`LLM_MODEL` with their own, tighter limits: see [agents.md](agents.md).

Cost controls: a small model; digests instead of raw scanner output; structured
JSON output with `max_tokens` bounds (narrate 2K, triage 1K per call of 8
gaps); a response cache keyed on `sha256(model + prompt)`; batches for the eval;
and a budget guard that stops before a call could pass `LLM_BUDGET_USD`. Every
call is logged to `out/llm-usage.jsonl`, and the report footer shows the run's
cost. Measured on the sample app's real scan (41 gap rules) while triage ran on
Sonnet 5: narrate on Haiku 4.5, 1 call, $0.014; triage, 6 calls, $0.097. With
triage now on Haiku 4.5 (about a fifth of Sonnet's price per token), a full run
should come to roughly $0.03, within the original spec's $0.05 target; that
figure is an estimate until the next measured run.

**First eval baseline** (Haiku 4.5, one Message Batch, $0.009): accuracy 0.64,
`none` precision 1.0, `none` recall 0.1, no invalid outputs. Every clear match
landed on the right control, but the model said `none` for only 1 of the 10 gaps
that no control fits. Eight of those nine misses put ordinary infrastructure
rules (health checks, probes, backups, CPU limits) on ISO/IEC 42001 or EU AI Act
controls.

**Scoped variant** ([issue #32](https://github.com/cdevarenne/okf-grc-skill/issues/32);
[`examples/triage-eval-scoped.json`](../examples/triage-eval-scoped.json), $0.022):
giving triage each control's framework scope and each gap's target files
removed every infrastructure-to-AI-control miss, but the held-out result did not
move: accuracy 0.667 and `none` recall 0.2 for both variants on 15 held-out
cases. The model still prefers a plausible control to `none`; with the AI
controls ruled out, those gaps land on SOC 2 controls instead. The tune split
improved (0.64 to 0.84), but it shaped the diagnosis, so it is not evidence.
This is why triage only proposes: a person decides.

**Confidence cutoffs and a stronger model** (issue #32;
[`triage-eval-cutoffs-haiku.json`](../examples/triage-eval-cutoffs-haiku.json), $0 from
the response cache; [`triage-eval-cutoffs-sonnet.json`](../examples/triage-eval-cutoffs-sonnet.json),
$0.092). The eval also scores treating `low` (or `low` and `medium`) confidence
proposals as `none`; the cutoff is chosen on `tune` and reported on `holdout`:

| Model | Input | Cutoff (chosen on tune) | Holdout accuracy | Holdout `none` recall | Holdout AI cases |
|---|---|---|---|---|---|
| Haiku 4.5 | baseline | as-is | 0.667 | 0.2 | 5/5 |
| Haiku 4.5 | scoped | low+medium → none | 0.867 | 0.8 | 4/5 |
| Sonnet 5 | baseline | as-is | 0.800 | 0.8 | 5/5 |
| Sonnet 5 | scoped | low → none | 0.933 | 1.0 | 5/5 |

Haiku never answers with `low` confidence here, so only the `medium` cutoff
moves it. Sonnet 5 with the scoped input and a `low` cutoff misses one of 15
holdout cases. Caveat: twelve configurations were compared on 15 holdout cases
(one case is about 7 points), so the winner needed confirming on fresh cases.

**Confirm holdout and the default** (issue #32; decision rule written before the
run; [`triage-eval-confirm-haiku.json`](../examples/triage-eval-confirm-haiku.json),
[`triage-eval-confirm-sonnet.json`](../examples/triage-eval-confirm-sonnet.json),
$0.043 together). 25 new cases, including traps in AI-component files whose
right answer is not an AI control:

| Candidate (cutoff chosen on tune) | Confirm accuracy | Confirm `none` recall | Confirm AI cases |
|---|---|---|---|
| Haiku 4.5, scoped, low+medium → none | 0.80 | 0.875 | 6/7 |
| Sonnet 5, scoped, low → none | **0.92** | **1.0** | **7/7** |

Both cleared the pre-registered bar (≥ 0.75 on `none` recall and on AI cases);
Sonnet 5 led by three cases, more than the one-case margin that would have
favored the cheaper Haiku, so it became `make triage`'s default at first.

**Run-to-run variance** ([`triage-eval-variance-haiku.json`](../examples/triage-eval-variance-haiku.json),
[`triage-eval-variance-sonnet.json`](../examples/triage-eval-variance-sonnet.json), $0.10):
three fresh runs of each candidate on the confirm split, cache off.

| Candidate | Confirm accuracy, 3 runs | Confirm AI cases, 3 runs | Deciding run above |
|---|---|---|---|
| Haiku 4.5, low+medium → none | 0.88, 0.76, 0.84 | 7/7, 7/7, 7/7 | 0.80, 6/7 |
| Sonnet 5, low → none | 0.80, 0.88, 0.88 | 5/7, 6/7, 6/7 | 0.92, 7/7 |

The run that decided the default was Sonnet 5's best: every fresh run scored
lower. Over repeats the two candidates overlap on accuracy, and Haiku is steadier
on the AI cases, at about a fifth of the cost. A single run was not enough
evidence to separate them, so the default moved back to Haiku 4.5 with the
`low+medium` cutoff: equal within noise on accuracy, steadier on AI cases, and
cheaper. `LLM_MODEL=claude-sonnet-5 make triage TRIAGE_ARGS="--abstain-on low"`
runs the Sonnet configuration.

Prompt caching is requested but does not take effect on Haiku 4.5 today: its
minimum cacheable prefix is 4,096 tokens and the bundle digest is smaller. The
ledger's `cache_read_input_tokens` shows this honestly; it starts caching on its
own if the bundle grows, or with `LLM_MODEL=claude-sonnet-5`.
