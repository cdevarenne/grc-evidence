"""What LLM text may claim about a control, shared by narration and agent drafts: the four statuses, never
"satisfied", and only numbers taken from the data it was given."""

from __future__ import annotations

import re

STATUSES = ("not-satisfied", "no-violations-detected", "not-assessed", "not-applicable")
FORBIDDEN = re.compile(r"(?<![\w-])(satisfied|compliant|passed)\b", re.IGNORECASE)
STATUS = re.compile("|".join(STATUSES))
NUMBER = re.compile(r"\d+(?:\.\d+)*")
NOT_SATISFIED = re.compile(r"\bnot\s+satisfied\b", re.IGNORECASE)


def normalize(text: str) -> str:
    """"Not satisfied" in plain words, read as the status token: not a claim that a control is satisfied."""
    return NOT_SATISFIED.sub("not-satisfied", text)
