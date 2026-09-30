"""Record the replay fixtures the offline tests use: one narrate call and a baseline and a scoped triage call.

Metered: run once with LLM_MODE=record and an API key. Costs well under $0.05 on Haiku.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "grc-continuous-compliance" / "scripts"))

from okf_grc.digest import bundle_digest, scan_digest  # noqa: E402
from okf_grc.llm import LLM  # noqa: E402
from okf_grc.map_findings import map_findings  # noqa: E402
from okf_grc.narrate import narrate  # noqa: E402
from okf_grc.okf_lib import load_bundle  # noqa: E402
from okf_grc.triage import triage  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


def main() -> None:
    if os.environ.get("LLM_MODE") != "record":
        sys.exit("set LLM_MODE=record (metered) to record fixtures")
    llm = LLM.from_env(ROOT / "out")
    llm.fixtures = FIXTURES / "llm"
    bundle = load_bundle(FIXTURES / "bundle")
    mapping = map_findings(bundle, json.loads((FIXTURES / "findings.json").read_text(encoding="utf-8")))
    narratives, errors = narrate(llm, bundle_digest(bundle), mapping)
    proposals = triage(llm, bundle_digest(bundle), scan_digest(mapping)["gaps"])
    scoped = triage(
        llm, bundle_digest(bundle, scoped=True), scan_digest(mapping, targets=True)["gaps"], variant="scoped"
    )
    report = {"narrate_errors": errors, "narrated": sorted(narratives), "proposals": proposals, "scoped": scoped}
    print(json.dumps(report, indent=2))
    print(f"spent ${llm.spent_usd():.4f}; fixtures in {llm.fixtures.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
