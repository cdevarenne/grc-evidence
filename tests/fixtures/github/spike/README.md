# Spike: which branch-rule endpoints a read-only token can read

Plan Task 5 (Spec H Part A), run by the owner on 2026-10-06. The decision is in
[`docs/limits.md`](../../../../docs/limits.md), "Repository settings". No token
is recorded here.

Token: fine-grained, read-only, on the owner's repos (Contents, Metadata and
Administration: read).

```bash
for repo in cdevarenne/grc-evidence GoogleCloudPlatform/microservices-demo; do
  gh api -i repos/$repo/rules/branches/main
  gh api -i repos/$repo/branches/main/protection
  gh api graphql -f query="query{repository(owner:\"${repo%/*}\",name:\"${repo#*/}\"){branchProtectionRules(first:5){nodes{pattern requiredApprovingReviewCount}}}}"
done
```

| Read | `cdevarenne/grc-evidence` (owned) | `GoogleCloudPlatform/microservices-demo` | Permission GitHub names (`X-Accepted-GitHub-Permissions`) |
|---|---|---|---|
| `rules/branches/main` (rulesets) | `200`, `[]` | `200`, `[]` | `metadata=read` |
| `branches/main/protection` (classic) | `404`, "Branch not protected" | `403` | `administration=read` |
| GraphQL `branchProtectionRules` | `nodes: []` | `FORBIDDEN`: "Resource not accessible by personal access token" | — |

Not run: the same reads with the Actions `GITHUB_TOKEN`.
