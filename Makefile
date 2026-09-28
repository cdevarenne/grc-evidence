include tools.lock

SCRIPTS := .claude/skills/grc-continuous-compliance/scripts
PY := uv run python
PY_LLM := uv run --extra llm python
TOOLBIN := $(CURDIR)/.tools/bin
export PATH := $(TOOLBIN):$(PATH)
export TRIVY_CACHE_DIR := $(CURDIR)/.tools/trivy-cache
OKF := reference-agent @ git+https://github.com/GoogleCloudPlatform/open-knowledge-format@$(OKF_COMMIT)

.PHONY: bootstrap scan narrate triage eval-triage render test test-integration examples clean

bootstrap:
	uv sync
	./scripts/bootstrap.sh

scan:
	$(PY) $(SCRIPTS)/run_scan.py --target app --out out
	$(PY) $(SCRIPTS)/map_findings.py --knowledge knowledge --out out
	$(PY) $(SCRIPTS)/to_oscal.py --knowledge knowledge --out out
	$(PY) $(SCRIPTS)/render_report.py --knowledge knowledge --out out

narrate:
	$(PY_LLM) $(SCRIPTS)/narrate.py --knowledge knowledge --out out
	$(PY) $(SCRIPTS)/render_report.py --knowledge knowledge --out out

triage:
	$(PY_LLM) $(SCRIPTS)/triage.py --knowledge knowledge --out out

eval-triage:
	$(PY_LLM) $(SCRIPTS)/eval_triage.py --knowledge knowledge --out out $(EVAL_ARGS)

render:
	mkdir -p out
	uvx --python 3.14 --from "$(OKF)" reference-agent visualize --bundle knowledge --out out/knowledge-viz.html

test:
	uv run pytest
	$(TOOLBIN)/conftest verify -p policies/rego --no-color
	$(TOOLBIN)/semgrep --test policies/semgrep

test-integration:
	uv run pytest -m integration

examples: scan
	cp out/report.md examples/report.md

clean:
	rm -rf out
