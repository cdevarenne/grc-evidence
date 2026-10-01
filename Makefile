include src/okf_grc/data/tools.lock

GRC := uv run grc
PY_LLM := uv run --extra llm python -m
TOOLBIN := $(CURDIR)/.tools/bin
export PATH := $(TOOLBIN):$(PATH)
export TRIVY_CACHE_DIR := $(CURDIR)/.tools/trivy-cache
OKF := reference-agent @ git+https://github.com/GoogleCloudPlatform/open-knowledge-format@$(OKF_COMMIT)

.PHONY: bootstrap scan narrate triage eval-triage render test test-integration examples clean

bootstrap:
	uv sync
	$(GRC) bootstrap

scan:
	$(GRC) run --target app --knowledge knowledge --out out

narrate:
	$(PY_LLM) okf_grc.narrate --knowledge knowledge --out out
	$(GRC) report --knowledge knowledge --out out

triage:
	$(PY_LLM) okf_grc.triage --knowledge knowledge --out out $(TRIAGE_ARGS)

eval-triage:
	$(PY_LLM) okf_grc.eval_triage --knowledge knowledge --out out $(EVAL_ARGS)

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
	mkdir -p examples/oscal
	cp out/oscal/*.json examples/oscal/
	cp out/run.json examples/run.json

clean:
	rm -rf out
