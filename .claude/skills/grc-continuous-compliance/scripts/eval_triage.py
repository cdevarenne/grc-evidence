"""Score triage proposals against a labeled set: accuracy, abstention (`none`) quality, invalid rate, cost.

Cases carry a `split`: `tune` (seen while diagnosing, issue #32) or `holdout` (labeled before any run;
the headline). Each requested variant runs on each split, all in one Message Batch.
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
SPLITS = ("tune", "holdout")


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
        "misses": [
            {"rule": c["rule"], "expected": c["expected"], "got": p["proposal"]}
            for c, p in pairs
            if p["proposal"] != c["expected"]
        ],
    }


def evaluate(llm: LLM, bundle: Bundle, cases: list[Json], variants: list[str]) -> dict[str, dict[str, Json]]:
    """{variant: {split: score}}. Every (variant, split) is chunked on its own, then all go in one batch."""
    groups: dict[tuple[str, str], tuple[list[Json], dict[str, Any], set[str]]] = {}
    requests: dict[str, Any] = {}
    for variant in variants:
        bundle_doc = bundle_digest(bundle, scoped=variant == "scoped")
        for split in SPLITS:
            split_cases = [c for c in cases if c["split"] == split]
            chunks = chunk_requests(bundle_doc, [gap(c) for c in split_cases], variant)
            groups[variant, split] = (split_cases, chunks, set(bundle_doc))
            requests |= {f"{variant}/{split}/{cid}": req for cid, (req, _) in chunks.items()}
    outputs = llm.complete_batch(requests)
    results: dict[str, dict[str, Json]] = {v: {} for v in variants}
    for (variant, split), (split_cases, chunks, keys) in groups.items():
        mine = {cid: outputs[f"{variant}/{split}/{cid}"] for cid in chunks}
        results[variant][split] = score(split_cases, parse(mine, chunks, keys))
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
    path = args.out / "eval" / f"triage-{datetime.now(UTC).date().isoformat()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"eval-triage ({llm.mode}, ${doc['cost_usd']}) -> {path}")
    print(f"{'variant':<9} {'split':<8} {'cases':>5} {'acc':>6} {'none P':>7} {'none R':>7} {'invalid':>8}")
    for variant, splits in results.items():
        for split, r in splits.items():
            print(f"{variant:<9} {split:<8} {r['cases']:>5} {r['accuracy']:>6} {r['none_precision']!s:>7} "
                  f"{r['none_recall']!s:>7} {r['invalid_rate']:>8}")


if __name__ == "__main__":
    main()
