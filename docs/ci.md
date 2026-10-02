# CI

How this repository tests and releases itself, and how to run okf-grc in your
own pipeline.

## This repository

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs `make bootstrap`,
`make audit` (see below), `make test` (unit tests, `grc check`, Rego and Semgrep rule tests), and
`make test-integration` (a full scan of the sample app) on every push to `main`
and every pull request. uv's package cache keeps the scanner installs fast;
Trivy's vulnerability database is cached once a day.

[`.github/workflows/release.yml`](../.github/workflows/release.yml) runs when a
version tag is pushed: it fails first unless the tag equals `v` plus the
package version, runs the same tests, and publishes a GitHub release. Adopters
install that tag.

Both workflows pin every action to a commit SHA, keep the token read-only
except where the release needs `contents: write`, do not persist credentials,
and pass no `${{ }}` expression into a shell command.

## Supply-chain audit

`make audit` scans the engine's own dependencies, not the deliberately
vulnerable `app/`: `uv.lock` and the Python scanners' hash-pinned requirements
in `src/okf_grc/data/locks/`, with the pinned Trivy; and the workflows, with
zizmor (a dev dependency, so `uv.lock` pins it by hash). It fails on a high or
critical vulnerability that has a fixed version, unless
[`audit-ignore.yaml`](../audit-ignore.yaml) records a reviewed exception: one
exact finding, a reason, and an expiry at most 90 days out, after which the audit
fails again until someone reviews it. CI and the release workflow both run it.

## Dependency updates

[`.github/dependabot.yml`](../.github/dependabot.yml) opens one grouped pull
request a week for the pinned actions and one for `uv.lock`. Security alerts
stay off because `app/` is deliberately vulnerable, and Dependabot does not
touch the scanner locks: change a scanner version in `tools.lock` and run
`make lock-scanners` instead.

## Your own pipeline

A starting point for a repository set up with `grc init` (see
[new-repo.md](new-repo.md)). It has not been run yet: Spec F Part B builds and
proves it on `microservices-demo`, including a gate on control status and a
nightly scan.

```yaml
name: compliance
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
  scan:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7  # v10.2.0
      - run: uv tool install git+https://github.com/cdevarenne/okf-grc-skill@v1.5.0
      - run: grc bootstrap
      - run: grc check
      - run: grc run --require-clean
      - run: grc gate --summary "$GITHUB_STEP_SUMMARY"  # fails if compliance got worse than expected/
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7.0.1
        with:
          name: compliance
          path: out/
```

`grc gate` compares the run with `expected/control-status.json`, a baseline you
commit (`grc gate --write-baseline` creates it with each control's status and
each mapped finding). It fails when a control moves to `not-satisfied`, when a
finding not in the baseline is at or above `--fail-on` (default `high`), or when
a suppression has expired, and writes the status table to the job summary. A
control already `not-satisfied` does not fail again, but a new finding in it
does; update the baseline in the same pull request when a change is accepted.

A finding is identified by tool, rule, and file: a version bump on a package
that is still vulnerable is not new, and neither is a second instance of a rule
in a file that already had one. Severity `unknown` (most Checkov rules) never
reaches a `--fail-on` level; accepted risks are left out. A baseline written
before 1.3.0 records statuses only, so the gate checks statuses only and says so.

`out/run.json` names the commit, the engine and scanner versions, the layout,
and the sha256 of every output, so the uploaded artifact is traceable to the
change that produced it. No LLM step runs in this job; narration and triage need
a model API key or a person's Claude plan, and stay local.
