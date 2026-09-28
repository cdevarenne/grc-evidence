"""Score triage proposals against a labeled set: accuracy, abstention (`none`) quality, invalid rate, cost."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from digest import bundle_digest
from llm import LLM
from okf_lib import load_bundle
from triage import triage

Json = dict[str, Any]


def load_cases(path: Path) -> list[Json]:
    """Eval cases: {rule: 'tool:rule_id', message, expected: control key | 'none'}."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def gap(case: Json) -> Json:
    tool, _, rule_id = case["rule"].partition(":")
    return {"tool": tool, "rule_id": rule_id, "message": case["message"], "reason": "no-rule-match", "count": 1}


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--cases", type=Path, default=Path("tests/fixtures/triage_eval.yaml"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    cases = load_cases(args.cases)
    llm = LLM.from_env(args.out)
    proposals = triage(llm, bundle_digest(load_bundle(args.knowledge)), [gap(c) for c in cases], batch=True)
    result = score(cases, proposals) | {
        "model": llm.model,
        "mode": llm.mode,
        "cost_usd": round(llm.spent_usd(), 6),
        "cost_per_case_usd": round(llm.spent_usd() / len(cases), 6) if cases else 0.0,
    }
    path = args.out / "eval" / f"triage-{datetime.now(UTC).date().isoformat()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"eval-triage: accuracy {result['accuracy']}, none P/R {result['none_precision']}/"
          f"{result['none_recall']}, invalid {result['invalid_rate']}, ${result['cost_usd']} -> {path}")


if __name__ == "__main__":
    main()
