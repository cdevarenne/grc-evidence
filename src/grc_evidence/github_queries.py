"""GraphQL reads used by the collectors: constants only, and never a mutation.

Each query also asks for `rateLimit { cost remaining }`, which the ledger records per collection.
`totalCount` beside a list of 100 lets a collector see a list that was cut off.
"""

# The name of the default branch.
DEFAULT_BRANCH = """query($owner: String!, $name: String!) {
  rateLimit { cost remaining }
  repository(owner: $owner, name: $name) { defaultBranchRef { name } }
}
"""

# The workflow files at an expression such as `HEAD:.github/workflows`.
WORKFLOWS = """query($owner: String!, $name: String!, $expr: String!) {
  rateLimit { cost remaining }
  repository(owner: $owner, name: $name) {
    object(expression: $expr) { ... on Tree { entries { name type object { ... on Blob { text isTruncated } } } } }
  }
}
"""

# One page of merged pull requests, newest update first, with reviews and the checks on the merge commit.
MERGED_PRS = """query($owner: String!, $name: String!, $cursor: String) {
  rateLimit { cost remaining }
  repository(owner: $owner, name: $name) {
    pullRequests(states: MERGED, first: 50, after: $cursor, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title updatedAt mergedAt baseRefName headRefOid
        author { login }
        mergedBy { login }
        mergeCommit {
          oid
          statusCheckRollup {
            contexts(first: 100) {
              totalCount
              nodes { __typename ... on CheckRun { name conclusion } ... on StatusContext { context state } }
            }
          }
        }
        reviews(first: 100) {
          totalCount
          nodes { author { __typename login } state submittedAt authorCanPushToRepository commit { oid } }
        }
      }
    }
  }
}
"""
