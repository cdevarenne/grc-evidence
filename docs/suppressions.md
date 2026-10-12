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
a coverage gap is rejected when the bundle loads.

One suppression may cover one rule in several named files: `finding.targets`
lists two or more files in place of `target`, and one owner, reason, expiry and
signature cover them all (2.2.0). Every file is named; a new file with the same
advisory is a new finding until a person adds it. A listed file that matches no
finding, while others do, is listed under **Unused suppressions** with its
target (`unused_targets` in `mapping.json`). `map_findings.py --today`
sets the date used for expiry; a suppression approved after that date (a
reviewer's date east of UTC, or a typo) is **pending**: not applied, and listed
under **Pending suppressions** so it is never silently ignored. A suppression with no `verified` entry by a person (`human:...`) is pending
too, whatever its dates: a drafted acceptance never hides a finding before
someone signs it (2.0.1).

## Drafting one

`grc suppress draft` writes a pending suppression from the last scan
(`out/mapping.json`), with every field except the reason and `verified` (2.2.0):

```sh
grc suppress draft --tool trivy --rule-id CVE-2026-78669 \
  --target upstream/src/frontend/go.mod --target upstream/src/shippingservice/go.mod \
  --kind accepted-risk --days 30 --owner human:jdoe
```

It refuses a target with no such finding in the last scan, an accepted risk on
a coverage gap, a finding another suppression already names (renewing or
widening one is a person's edit), `--days` outside 1 to 90, and an owner that
is not `human:<name>`. The `# Reason` section lists what the scanner reported
for each target, under a draft marker line; an accepted risk also gets a
`# Compensating control` section with the marker. Write each section, delete
the marker lines, and add `verified`. Until then `grc check` fails on the draft
(not verified by a person) and the scan lists it as pending; a signed file that
still has a marker line fails to load.

The two sample suppressions were approved on 2026-09-28 and expire on
2026-12-27, deliberately: from 2026-12-13 a scan lists them under **Expiring
soon**, and from 2026-12-28 under **Expired suppressions**, with their findings
counted again. That is the workflow working, not the repo going stale; renewing
one means a new review and a new `verified` entry.
