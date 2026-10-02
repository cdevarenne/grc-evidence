include src/okf_grc/data/tools.lock

GRC := uv run grc
GRC_LLM := uv run --extra llm grc
PY_LLM := uv run --extra llm python -m
TOOLBIN := $(CURDIR)/.tools/bin
export PATH := $(TOOLBIN):$(PATH)
export TRIVY_CACHE_DIR := $(CURDIR)/.tools/trivy-cache
OKF := reference-agent @ git+https://github.com/GoogleCloudPlatform/open-knowledge-format@$(OKF_COMMIT)

.PHONY: bootstrap lock-scanners sync-base audit examples-llm scan narrate triage eval-triage render test test-integration examples clean

bootstrap:
	uv sync
	$(GRC) bootstrap

# Regenerate the Python scanners' hash-pinned requirements after changing their versions in tools.lock.
LOCKS := src/okf_grc/data/locks
lock-scanners:
	mkdir -p $(LOCKS)/semgrep $(LOCKS)/checkov
	echo "semgrep==$(SEMGREP_VERSION)" | uv pip compile --quiet --universal --generate-hashes --python-version $(SEMGREP_PYTHON) - -o $(LOCKS)/semgrep/requirements.txt
	echo "checkov==$(CHECKOV_VERSION)" | uv pip compile --quiet --universal --generate-hashes --python-version $(CHECKOV_PYTHON) - -o $(LOCKS)/checkov/requirements.txt

# Supply chain: the engine's own dependencies (not the deliberately vulnerable app/) and the workflows.
# Fails on a high or critical vulnerability that has a fix, unless audit-ignore.yaml records a reviewed exception.
audit:
	$(TOOLBIN)/trivy fs --quiet --scanners vuln --ignore-unfixed --severity HIGH,CRITICAL --exit-code 1 \
	  --ignorefile audit-ignore.yaml --skip-dirs app --skip-dirs .tools --skip-dirs out --skip-dirs .venv .
	uv run zizmor --no-progress .github/workflows

# knowledge/ and policies/ hold copies of the base bundle; edit src/okf_grc/data/ and sync (#64).
sync-base:
	$(GRC) sync-base

scan: sync-base
	$(GRC) run --target app --knowledge knowledge --out out

narrate:
	$(GRC_LLM) narrate --knowledge knowledge --out out

triage:
	$(GRC_LLM) triage --knowledge knowledge --out out $(TRIAGE_ARGS)

eval-triage:
	$(PY_LLM) okf_grc.eval_triage --knowledge knowledge --out out $(EVAL_ARGS)

render:
	mkdir -p out
	uvx --python 3.14 --from "$(OKF)" reference-agent visualize --bundle knowledge --out out/knowledge-viz.html

test:
	uv run ruff check
	uv run mypy
	uv run pytest
	$(GRC) check
	$(TOOLBIN)/conftest verify -p policies/rego --no-color
	$(TOOLBIN)/semgrep --test policies/semgrep

test-integration:
	uv run pytest -m integration

examples: scan
	cp out/report.md examples/report.md
	mkdir -p examples/oscal
	cp out/oscal/*.json examples/oscal/
	cp out/run.json examples/run.json

# The examples with LLM prose: narrate the fresh scan (LLM_MODE=anthropic or claude-cli), then copy the
# report and the run manifest narrate rewrote. A plain `make examples` afterwards would drop the prose again.
examples-llm: examples
	$(GRC_LLM) narrate --knowledge knowledge --out out
	cp out/report.md examples/report.md
	cp out/run.json examples/run.json

clean:
	rm -rf out
