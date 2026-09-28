"""eval_triage: scoring rewards correct abstention as much as correct matches."""

from eval_triage import gap, score


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
    assert gap({"rule": "trivy:DS-0026", "message": "No HEALTHCHECK", "expected": "none"})["rule_id"] == "DS-0026"
