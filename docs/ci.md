# CI

How this repository tests and releases itself, and how to run okf-grc in your
own pipeline.

## This repository

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs `make bootstrap`,
`make test` (unit tests, `grc check`, Rego and Semgrep rule tests), and
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
      - run: uv tool install git+https://github.com/cdevarenne/okf-grc-skill@v1.1.0
      - run: grc bootstrap
      - run: grc check
      - run: grc run
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7.0.1
        with:
          name: compliance
          path: out/
```

`out/run.json` names the commit, the engine and scanner versions, the layout,
and the sha256 of every output, so the uploaded artifact is traceable to the
change that produced it. No LLM step runs in this job; narration and triage need
a model API key or a person's Claude plan, and stay local.
