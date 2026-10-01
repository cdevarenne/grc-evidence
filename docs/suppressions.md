# Suppressions

How reviewed, expiring decisions about single findings change how they count.

A suppression is a reviewed decision about one exact finding, stored in
[`knowledge/suppressions/`](../knowledge/suppressions/) with an owner, a reason,
and an expiry at most 90 days after approval. It changes how the finding
counts, never whether it is shown:

- **`false-positive`**: the finding no longer counts toward its control or the
  coverage-gap list, and is listed under **Suppressed** in the report and in the
  OSCAL `remarks`.
- **`accepted-risk`**: the finding stays on its control, which stays
  `not-satisfied`; it is marked accepted in the report and recorded in OSCAL as
  a risk with status `deviation-approved`.

An expired suppression stops applying (the finding counts again and the report
lists it under **Expired suppressions**); one within 14 days of expiry is listed
under **Expiring soon**; one that matches no finding is listed under **Unused
suppressions**. Suppressions match on tool, rule id, target, and
optionally a message substring; there are no wildcards, and an accepted risk on
a coverage gap is rejected when the bundle loads. `map_findings.py --today`
sets the date used for expiry; a suppression approved after that date (a
reviewer's date east of UTC, or a typo) is **pending**: not applied, and listed
under **Pending suppressions** so it is never silently ignored.

The two sample suppressions were approved on 2026-09-28 and expire on
2026-12-27, deliberately: from 2026-12-13 a scan lists them under **Expiring
soon**, and from 2026-12-28 under **Expired suppressions**, with their findings
counted again. That is the workflow working, not the repo going stale; renewing
one means a new review and a new `verified` entry.
