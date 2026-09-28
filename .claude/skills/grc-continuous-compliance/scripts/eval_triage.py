"""Score triage proposals against a labeled set: accuracy, abstention (`none`) quality, invalid rate, cost.

Cases carry a `split`: `tune` (seen while diagnosing, issue #32), `holdout` (labeled before its first
run), or `confirm` (a second, fresh holdout for choosing the default). Each requested variant runs on
each split, all in one Message Batch; confidence cutoffs are selected on `tune` only.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from digest import bundle_digest
from llm import LLM, LLMError
from okf_lib import Bundle, load_bundle
from triage import VARIANTS, chunk_requests, parse

Json = dict[str, Any]
SPLITS = ("tune", "holdout", "confirm")  # confirm: a fresh holdout for the default decision
AI_PREFIXES = ("iso42001:", "eu-ai-act:")
# Confidence cutoffs (issue #32): treat proposals at these confidence levels as `none`. The cutoff is
# selected on `tune` and only reported on `holdout`, so the holdout number stays honest.
CUTOFFS = {"as-is": (), "low->none": ("low",), "low+medium->none": ("low", "medium")}


def load_cases(path: Path) -> list[Json]:
    """Eval cases: {rule: 'tool:rule_id', message, target, split: tune|holdout, expected: control key | 'none'}."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def gap(case: Json) -> Json:
    """The gap a real scan would produce for this case (the `baseline` variant ignores `targets`)."""
    tool, _, rule_id = case["rule"].partition(":")
    return {
        "tool": tool, "rule_id": rule_id, "message": case["message"], "reason": "no-rule-match", "count": 1,
        "targets": [case["target"]],
    }


def _accuracy(pairs: list[tuple[Json, Json]]) -> float | None:
    return round(sum(p["proposal"] == c["expected"] for c, p in pairs) / len(pairs), 3) if pairs else None


def apply_cutoff(proposals: list[Json], abstain_on: tuple[str, ...]) -> list[Json]:
    """Proposals whose confidence is in `abstain_on` become `none`; `none` and `invalid` stay as they are."""
    return [
        p | {"proposal": "none"} if p["proposal"] not in ("none", "invalid") and p.get("confidence") in abstain_on else p
        for p in proposals
    ]


def select_cutoff(tune_scores: dict[str, Json]) -> str:
    """Best tune accuracy; on a tie, the cutoff that abstains least (CUTOFFS order)."""
    return max(CUTOFFS, key=lambda name: (tune_scores[name]["accuracy"], -list(CUTOFFS).index(name)))


def score(cases: list[Json], proposals: list[Json]) -> Json:
    """Metrics over paired (case, proposal). `none` precision/recall measures abstention quality."""
    pairs = list(zip(cases, proposals, strict=True))
    n = len(pairs)
    exact = sum(p["proposal"] == c["expected"] for c, p in pairs)
    said_none = [(c, p) for c, p in pairs if p["proposal"] == "none"]
    is_none = [(c, p) for c, p in pairs if c["expected"] == "none"]
    true_none = sum(c["expected"] == "none" for c, _ in said_none)
    return {
        "cases": n,
        "accuracy": round(exact / n, 3) if n else 0.0,
        "none_precision": round(true_none / len(said_none), 3) if said_none else None,
        "none_recall": round(true_none / len(is_none), 3) if is_none else None,
        "invalid_rate": round(sum(p["proposal"] == "invalid" for _, p in pairs) / n, 3) if n else 0.0,
        "ai_accuracy": _accuracy([(c, p) for c, p in pairs if c["expected"].startswith(AI_PREFIXES)]),
        "misses": [
            {"rule": c["rule"], "expected": c["expected"], "got": p["proposal"]}
            for c, p in pairs
            if p["proposal"] != c["expected"]
        ],
    }


def evaluate(llm: LLM, bundle: Bundle, cases: list[Json], variants: list[str]) -> dict[str, Json]:
    """{variant: {"selected_cutoff", split: {"cutoffs": {name: score}, "answers": [...]}}}.

    Every (variant, split) is chunked on its own, then all go in one batch. Each cutoff is scored on
    each split; the cutoff is selected on `tune` alone.
    """
    groups: dict[tuple[str, str], tuple[list[Json], dict[str, Any], set[str]]] = {}
    requests: dict[str, Any] = {}
    for variant in variants:
        bundle_doc = bundle_digest(bundle, scoped=variant == "scoped")
        for split in SPLITS:
            split_cases = [c for c in cases if c["split"] == split]
            chunks = chunk_requests(bundle_doc, [gap(c) for c in split_cases], variant)
            groups[variant, split] = (split_cases, chunks, set(bundle_doc))
            requests |= {f"{variant}-{split}-{cid}": req for cid, (req, _) in chunks.items()}
    outputs = llm.complete_batch(requests)
    results: dict[str, Json] = {v: {} for v in variants}
    for (variant, split), (split_cases, chunks, keys) in groups.items():
        mine = {cid: outputs[f"{variant}-{split}-{cid}"] for cid in chunks}
        proposals = parse(mine, chunks, keys)
        results[variant][split] = {
            "cutoffs": {name: score(split_cases, apply_cutoff(proposals, on)) for name, on in CUTOFFS.items()},
            "answers": [
                {"rule": c["rule"], "expected": c["expected"], "proposal": p["proposal"], "confidence": p.get("confidence")}
                for c, p in zip(split_cases, proposals, strict=True)
            ],
        }
    for variant in variants:
        results[variant]["selected_cutoff"] = select_cutoff(results[variant]["tune"]["cutoffs"])
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--cases", type=Path, default=Path("tests/fixtures/triage_eval.yaml"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--variants", default=",".join(VARIANTS), help="comma-separated: baseline,scoped")
    args = parser.parse_args()
    variants = args.variants.split(",")
    if unknown := set(variants) - set(VARIANTS):
        parser.error(f"unknown variant(s): {sorted(unknown)}")
    cases = load_cases(args.cases)
    llm = LLM.from_env(args.out)
    try:
        results = evaluate(llm, load_bundle(args.knowledge), cases, variants)
    except LLMError as e:
        parser.exit(1, f"eval-triage: {e}\n")
    runs = len(variants) * len(cases)
    doc = {
        "model": llm.model,
        "mode": llm.mode,
        "cost_usd": round(llm.spent_usd(), 6),
        "cost_per_case_usd": round(llm.spent_usd() / runs, 6) if runs else 0.0,
        "results": results,
    }
    path = args.out / "eval" / f"triage-{datetime.now(UTC).date().isoformat()}-{llm.model}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"eval-triage ({llm.model}, {llm.mode}, ${doc['cost_usd']}) -> {path}")
    print("  * = cutoff selected on tune; read the other splits for that row")
    header = "".join(f" | {split + ' acc':>11} {'noneR':>5} {'AI':>4}" for split in SPLITS)
    print(f"  {'variant':<9} {'cutoff':<17}{header}")
    for variant, r in results.items():
        for name in CUTOFFS:
            mark = "*" if name == r["selected_cutoff"] else " "
            cells = "".join(
                f" | {c['accuracy']!s:>11} {c['none_recall']!s:>5} {c['ai_accuracy']!s:>4}"
                for c in (r[split]["cutoffs"][name] for split in SPLITS)
            )
            print(f"{mark} {variant:<9} {name:<17}{cells}")

if __name__ == "__main__":
    main()
