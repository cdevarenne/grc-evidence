"""Review intervals (Spec J §4.3): how long a person's verification of a concept stays valid.

A concept is due at its latest `human:` verification plus the interval `grc.yaml` sets for its type, or at its own
`stale_after`, whichever is earlier. `grc check` warns within `warn_before` of that date and fails after it. An
adopter cannot re-verify a base-bundle copy without drift, so an overdue copy only warns unless `review.base` is
`fail` (the engine's own repo). Suppressions keep their own `expires` and are not reviewed here.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from grc_evidence.config import Config
from grc_evidence.okf_lib import SUPPRESSION_TYPE, Bundle, Concept
from grc_evidence.window import parse_ts


def add_duration(start: date, duration: str) -> date:
    """`start` plus `Nd`, `Nm` or `Ny`; months and years are calendar months, clamped to the month's last day."""
    n, unit = int(duration[:-1]), duration[-1]
    if unit == "d":
        return start + timedelta(days=n)
    year, month = divmod(start.month - 1 + n * (12 if unit == "y" else 1), 12)
    year, month = start.year + year, month + 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def _verified_on(concept: Concept) -> date | None:
    """The UTC date of the latest verification by a person."""
    entries = concept.frontmatter.get("verified") or []
    stamps = entries if isinstance(entries, list) else [entries]
    days = [
        parse_ts(str(v["at"])).date()
        for v in stamps
        if isinstance(v, dict) and str(v.get("by", "")).startswith("human:") and v.get("at")
    ]
    return max(days, default=None)


def due_date(concept: Concept, config: Config) -> date | None:
    """When a person must verify `concept` again, or None when nothing sets a date."""
    interval = dict(config.review_by_type).get(concept.type, config.review_default)
    verified = _verified_on(concept)
    candidates = [add_duration(verified, interval)] if interval and verified else []
    if concept.stale_after:
        candidates.append(concept.stale_after)
    return min(candidates, default=None)


def review(bundle: Bundle, config: Config, base_paths: set[str], today: date) -> tuple[list[str], list[str]]:
    """(problems, warnings) for `grc check`. `base_paths` are the bundle paths of the base-bundle copies."""
    types = {c.type for c in bundle.concepts.values()}
    problems = [
        f"grc.yaml: review.by_type names {t!r}, which no concept in {config.knowledge} has"
        for t, _ in config.review_by_type
        if t not in types
    ]
    warnings: list[str] = []
    for concept in sorted(bundle.concepts.values(), key=lambda c: c.id):
        if concept.type == SUPPRESSION_TYPE or (due := due_date(concept, config)) is None:
            continue
        where = f"{config.knowledge}/{concept.path}"
        if today > due and concept.path in base_paths and config.review_base == "warn":
            warnings.append(f"{where}: review due {due}, overdue in the engine; upgrade when a release re-verifies it")
        elif today > due:
            problems.append(f"{where}: review due {due}: verify it again")
        elif add_duration(today, config.review_warn_before) >= due:
            warnings.append(f"{where}: review due {due}")
    return problems, warnings
