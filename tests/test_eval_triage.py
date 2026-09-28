"""eval_triage: scoring rewards correct abstention as much as correct matches."""

from pathlib import Path

from eval_triage import evaluate, gap, score
from llm_stub import StubLLM
from okf_lib import load_bundle


def test_score_measures_accuracy_and_abstention() -> None:
    cases = [
        {"rule": "a:1", "expected": "soc2:cc6.1"},
        {"rule": "a:2", "expected": "none"},
        {"rule": "a:3", "expected": "none"},
        {"rule": "a:4", "expected": "soc2:cc7.1"},
    ]
    proposals = [{"proposal": "soc2:cc6.1"}, {"proposal": "none"}, {"proposal": "soc2:cc8.1"}, {"proposal": "none"}]
    result = score(cases, proposals)
    assert (result["accuracy"], result["none_precision"], result["none_recall"]) == (0.5, 0.5, 0.5)
    assert result["invalid_rate"] == 0.0 and len(result["misses"]) == 2


def test_invalid_proposals_are_counted() -> None:
    result = score([{"rule": "a:1", "expected": "none"}], [{"proposal": "invalid"}])
    assert (result["accuracy"], result["invalid_rate"], result["none_precision"]) == (0.0, 1.0, None)


def test_eval_case_becomes_a_gap() -> None:
    g = gap({"rule": "trivy:DS-0026", "message": "No HEALTHCHECK", "target": "app/Dockerfile", "expected": "none"})
    assert (g["rule_id"], g["targets"]) == ("DS-0026", ["app/Dockerfile"])


def test_evaluate_scores_each_variant_on_each_split_separately() -> None:
    cases = [
        {"rule": "t:a", "message": "m", "target": "app/x", "split": "tune", "expected": "none"},
        {"rule": "t:b", "message": "m", "target": "app/x", "split": "holdout", "expected": "soc2:cc6.1"},
    ]
    outputs = {
        "t:a": {"rule": "t:a", "proposal": "none", "rationale": "r", "confidence": "low"},
        "t:b": {"rule": "t:b", "proposal": "soc2:cc6.1", "rationale": "r", "confidence": "low"},
    }
    llm = StubLLM(outputs)
    results = evaluate(llm, load_bundle(Path(__file__).parent / "fixtures" / "bundle"), cases, ["baseline", "scoped"])
    assert {v: {s: r["accuracy"] for s, r in splits.items()} for v, splits in results.items()} == {
        "baseline": {"tune": 1.0, "holdout": 1.0},
        "scoped": {"tune": 1.0, "holdout": 1.0},
    }
    assert len(llm.requests) == 4  # 2 variants x 2 splits, one chunk each
    assert sum('"targets"' in r.user for r in llm.requests) == 2  # only the scoped requests carry targets
