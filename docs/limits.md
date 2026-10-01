# Limits

What okf-grc does not do, or does only partly. Read this before relying on a report.

- **Evidence, not attestation** A control with no violations is reported as
  `no-violations-detected`, never `satisfied`. Automated scans evidence a SOC 2
  criterion; they do not attest it.
- **Suppressions are exact and short-lived by design.** Each one matches a
  single finding, lasts at most 90 days, and needs a human review; there are no
  wildcard or bulk suppressions. Scanner-native inline skips (e.g.
  `checkov:skip`) are still honored by the scanners themselves and bypass this
  record.
- **Static manifests only** Helm or Kustomize output is not rendered before
  scanning.
- **Sized for the sample app.** Scanner JSON is read in memory, and the
  scanner set is fixed in `run_scan.py`.
- **Scan layout from `grc.yaml`** By default Conftest reads `k8s/**/*.{yaml,yml}`,
  `infra/**/*.tf`, and `ai-inventory.yaml` under the target. An optional
  `grc.yaml` at the repo root changes the target, the knowledge bundle, the AI
  inventory, Conftest's inputs, Checkov's frameworks and skipped paths, and the
  Semgrep and Rego policies, and the time each scanner may run (`scanner_timeout`,
  900 seconds by default; a scanner past it is stopped and named). See
  `src/okf_grc/config.py`. A target where
  Conftest finds no inputs stops the scan with an error.
- **LLM eval is small and single-run.** The triage eval has 65 labeled cases,
  labeled by the implementing agent and reviewed by the maintainer, not by an
  independent second labeler. Most configurations were run once; the two final
  candidates were re-run three times, which showed a spread of up to three
  cases per run, so differences of a case or two are not evidence.
- **The bundle is readable anywhere, reusable in part.** Any OKF tool can read
  it (`make render` uses the OKF reference visualizer). The control, crosswalk,
  and scanner concepts carry over to another project; the stack, the policies'
  `rule_ids`, the suppressions, and the AI inventory describe this repo's sample
  app. The engine knows only the three frameworks here: adding one means
  changing `okf_lib.py`, not just adding concepts.
- **Declared risk tier only** The AI Act tier is read from
  `app/ai-inventory.yaml`; nothing classifies the system. There is no
  conformity assessment, model evaluation, or NIST AI RMF control set
  (crosswalk links only).
