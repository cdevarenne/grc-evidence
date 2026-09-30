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

from okf_grc.digest import bundle_digest
from okf_grc.llm import LLM, LLMError
from okf_grc.okf_lib import Bundle, load_bundle
from okf_grc.triage import VARIANTS, apply_cutoff, chunk_requests, parse

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


def evaluate(
    llm: LLM,
    bundle: Bundle,
    cases: list[Json],
    variants: list[str],
    splits: tuple[str, ...] = SPLITS,
    repeats: int = 1,
) -> dict[str, Json]:
    """{variant: {"selected_cutoff"?, split: {"cutoffs", "answers", "runs"}}}.

    Every (variant, split) is chunked on its own, then all go in one batch. With `repeats` > 1 the same
    requests are sent that many times (use with the cache off) and each run is scored; `cutoffs` and
    `answers` are run 1, `runs` holds every run's cutoff scores. The cutoff is selected on `tune` alone,
    so `selected_cutoff` is present only when `tune` is among the splits.
    """
    groups: dict[tuple[str, str], tuple[list[Json], dict[str, Any], set[str]]] = {}
    requests: dict[str, Any] = {}
    for variant in variants:
        bundle_doc = bundle_digest(bundle, scoped=variant == "scoped")
        for split in splits:
            split_cases = [c for c in cases if c["split"] == split]
            chunks = chunk_requests(bundle_doc, [gap(c) for c in split_cases], variant)
            groups[variant, split] = (split_cases, chunks, set(bundle_doc))
            for run in range(repeats):
                requests |= {_cid(variant, split, cid, run, repeats): req for cid, (req, _) in chunks.items()}
    outputs = llm.complete_batch(requests)
    results: dict[str, Json] = {v: {} for v in variants}
    for (variant, split), (split_cases, chunks, keys) in groups.items():
        runs = []
        for run in range(repeats):
            mine = {cid: outputs[_cid(variant, split, cid, run, repeats)] for cid in chunks}
            proposals = parse(mine, chunks, keys)
            runs.append(
                {
                    "cutoffs": {name: score(split_cases, apply_cutoff(proposals, on)) for name, on in CUTOFFS.items()},
                    "answers": [
                        {"rule": c["rule"], "expected": c["expected"], "proposal": p["proposal"],
                         "confidence": p.get("confidence")}
                        for c, p in zip(split_cases, proposals, strict=True)
                    ],
                }
            )
        results[variant][split] = runs[0] | {"runs": [r["cutoffs"] for r in runs]}
    if "tune" in splits:
        for variant in variants:
            results[variant]["selected_cutoff"] = select_cutoff(results[variant]["tune"]["cutoffs"])
    return results


def _cid(variant: str, split: str, chunk: str, run: int, repeats: int) -> str:
    """Batch custom id; single runs keep the ids (and so the batch) of earlier evals."""
    return f"{variant}-{split}-{chunk}" + (f"-r{run}" if repeats > 1 else "")


def spread(values: list[float | None]) -> str:
    """'mean [min-max]' over runs, or the single value for one run."""
    nums = [v for v in values if v is not None]
    if not nums:
        return "None"
    if len(nums) == 1:
        return str(nums[0])
    return f"{sum(nums) / len(nums):.3f} [{min(nums)}-{max(nums)}]"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--cases", type=Path, default=Path("tests/fixtures/triage_eval.yaml"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--variants", default=",".join(VARIANTS), help="comma-separated: baseline,scoped")
    parser.add_argument("--splits", default=",".join(SPLITS), help="comma-separated: tune,holdout,confirm")
    parser.add_argument("--repeats", type=int, default=1, help="send each request N times (requires --no-cache)")
    parser.add_argument("--no-cache", action="store_true", help="call the API even for cached requests")
    args = parser.parse_args(argv)
    splits = tuple(args.splits.split(","))
    if unknown_splits := set(splits) - set(SPLITS):
        parser.error(f"unknown split(s): {sorted(unknown_splits)}")
    if args.repeats > 1 and not args.no_cache:
        parser.error("--repeats > 1 needs --no-cache, or every repeat would be the same cached answer")
    variants = args.variants.split(",")
    if unknown := set(variants) - set(VARIANTS):
        parser.error(f"unknown variant(s): {sorted(unknown)}")
    cases = load_cases(args.cases)
    llm = LLM.from_env(args.out)
    llm.use_cache = not args.no_cache
    try:
        results = evaluate(llm, load_bundle(args.knowledge), cases, variants, splits, args.repeats)
    except LLMError as e:
        parser.exit(1, f"eval-triage: {e}\n")
    answered = len(variants) * sum(c["split"] in splits for c in cases) * args.repeats
    doc = {
        "model": llm.model,
        "mode": llm.mode,
        "repeats": args.repeats,
        "cost_usd": round(llm.spent_usd(), 6),
        "cost_per_case_usd": round(llm.spent_usd() / answered, 6) if answered else 0.0,
        "results": results,
    }
    suffix = f"-x{args.repeats}" if args.repeats > 1 else ""
    path = args.out / "eval" / f"triage-{datetime.now(UTC).date().isoformat()}-{llm.model}{suffix}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"eval-triage ({llm.model}, {llm.mode}, ${doc['cost_usd']}) -> {path}")
    if args.repeats > 1:
        print(f"  {args.repeats} runs per request; mean [min-max] over runs")
        for variant, r in results.items():
            for name in CUTOFFS:
                for split in splits:
                    runs = r[split]["runs"]
                    print(f"  {variant:<9} {name:<17} {split:<8} acc {spread([x[name]['accuracy'] for x in runs]):<22}"
                          f" noneR {spread([x[name]['none_recall'] for x in runs]):<22}"
                          f" AI {spread([x[name]['ai_accuracy'] for x in runs])}")
        return
    print("  * = cutoff selected on tune; read the other splits for that row")
    header = "".join(f" | {split + ' acc':>11} {'noneR':>5} {'AI':>4}" for split in splits)
    print(f"  {'variant':<9} {'cutoff':<17}{header}")
    for variant, r in results.items():
        for name in CUTOFFS:
            mark = "*" if name == r.get("selected_cutoff") else " "
            cells = "".join(
                f" | {c['accuracy']!s:>11} {c['none_recall']!s:>5} {c['ai_accuracy']!s:>4}"
                for c in (r[split]["cutoffs"][name] for split in splits)
            )
            print(f"{mark} {variant:<9} {name:<17}{cells}")

if __name__ == "__main__":
    main()
