# Setting up a new repo

How to bring okf-grc into another repository: what `grc init` brings in, and what a person writes. This is also where document ingestion will be described once it exists ([#53](https://github.com/cdevarenne/okf-grc-skill/issues/53)).

The engine is the `okf-grc` package; its `grc` CLI runs the same pipeline
without this repo's Makefile or an agent. From the root of the repo to scan
(the install works once `v1.1.0` is tagged):

```
uv tool install git+https://github.com/cdevarenne/okf-grc-skill@v1.1.0
grc init        # knowledge/ and policies/ copied from the base bundle; starter grc.yaml,
                # ai-inventory.yaml, and one stack stub per src/*/ directory (never overwrites)
grc bootstrap   # the pinned scanners, into ./.tools
export PATH="$PWD/.tools/bin:$PATH"   # until grc finds them itself (#59)
grc check       # base copies unchanged, every concept reviewed by a person (stubs are not, yet)
grc run         # out/: findings, mapping, OSCAL, report, run.json
```

Edit `grc.yaml` to match the repo's layout, link each stack stub to the
controls its component implements, and set the AI risk tier in
`ai-inventory.yaml` with a recorded reason.

## What it brings in, and what you write

| Path | From | Who maintains it |
|---|---|---|
| `knowledge/controls/`, `crosswalk/`, `scanners/`, generic `policies/*.md`, `oscal/` | copied from the engine's base bundle | the engine; `grc check` reports any local change |
| `policies/rego/`, `policies/semgrep/` | copied from the engine | the engine; add your own rules next to them and list them in `grc.yaml` |
| `knowledge/index.md` | written by `grc init`, records `base_version` | you (the map), the engine (the version) |
| `knowledge/stack/` | one stub per `src/*/` directory | you: what each component is, and the controls it implements |
| `knowledge/suppressions/` | empty | you: one reviewed decision per finding |
| `ai-inventory.yaml` | a starter with `risk_tier` unset | you: components, AI systems and their SDKs, the risk tier with a reason |
| `grc.yaml` | every key with its default | you: the repo's real layout |

Every concept you write needs a `verified` entry from a person before
`grc check` passes. Your own scanner rules reach a control only through a
`rule_ids` line in a concept you write and review.
