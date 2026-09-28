"""eval_triage: scoring rewards correct abstention as much as correct matches."""

from pathlib import Path

from eval_triage import CUTOFFS, apply_cutoff, evaluate, gap, score, select_cutoff
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
    assert {
        v: {s: r[s]["cutoffs"]["as-is"]["accuracy"] for s in ("tune", "holdout")} for v, r in results.items()
    } == {"baseline": {"tune": 1.0, "holdout": 1.0}, "scoped": {"tune": 1.0, "holdout": 1.0}}
    assert results["scoped"]["holdout"]["answers"] == [
        {"rule": "t:b", "expected": "soc2:cc6.1", "proposal": "soc2:cc6.1", "confidence": "low"}
    ]
    assert results["baseline"]["selected_cutoff"] == "as-is"
    assert len(llm.requests) == 4  # 2 variants x 2 splits, one chunk each
    assert sum('"targets"' in r.user for r in llm.requests) == 2  # only the scoped requests carry targets


def _p(proposal: str, confidence: str) -> dict:
    return {"rule": "t:x", "proposal": proposal, "rationale": "r", "confidence": confidence}


def test_cutoff_turns_low_confidence_proposals_into_none() -> None:
    proposals = [_p("soc2:cc6.1", "low"), _p("soc2:cc6.1", "medium"), _p("soc2:cc6.1", "high"), _p("none", "low")]
    cut = apply_cutoff(proposals, CUTOFFS["low->none"])
    assert [p["proposal"] for p in cut] == ["none", "soc2:cc6.1", "soc2:cc6.1", "none"]
    assert cut[0]["cutoff_from"] == "soc2:cc6.1" and "cutoff_from" not in cut[3]
    assert [p["proposal"] for p in apply_cutoff(proposals, CUTOFFS["low+medium->none"])] == [
        "none", "none", "soc2:cc6.1", "none"
    ]
    invalid = {"rule": "t:x", "proposal": "invalid", "errors": ["e"]}
    assert apply_cutoff([invalid], CUTOFFS["low+medium->none"]) == [invalid]


def test_cutoff_is_selected_on_tune_and_ties_abstain_least() -> None:
    def scores(*accuracies: float) -> dict:
        return {name: {"accuracy": a} for name, a in zip(CUTOFFS, accuracies, strict=True)}

    assert select_cutoff(scores(0.6, 0.8, 0.7)) == "low->none"
    assert select_cutoff(scores(0.8, 0.8, 0.8)) == "as-is"


def test_ai_accuracy_counts_only_ai_labelled_cases() -> None:
    cases = [{"rule": "a:1", "expected": "iso42001:a.6"}, {"rule": "a:2", "expected": "eu-ai-act:art-50"},
             {"rule": "a:3", "expected": "none"}]
    proposals = [{"proposal": "iso42001:a.6"}, {"proposal": "iso42001:a.8"}, {"proposal": "none"}]
    assert score(cases, proposals)["ai_accuracy"] == 0.5
    assert score(cases[2:], proposals[2:])["ai_accuracy"] is None
