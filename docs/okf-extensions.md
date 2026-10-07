# OKF extension fields

The bundle is plain [OKF](https://github.com/GoogleCloudPlatform/open-knowledge-format) v0.2. These are the
fields it adds. Each has a JSON Schema in
[`src/grc_evidence/data/schemas/concepts/`](../src/grc_evidence/data/schemas/concepts/), and the engine checks the
same rules when it loads the bundle. A schema covers one concept's fields; rules that span fields, the body or the
bundle are load-time checks only. okflib checks OKF's own fields and signals (`type`, `generated`, `verified`,
`stale_after`).

## Controls

`SOC 2 Control`, `ISO/IEC 42001 Control`, `EU AI Act Article` ([schema](../src/grc_evidence/data/schemas/concepts/control.schema.json))

| Field | Rule | Checked by |
|---|---|---|
| `framework` | `soc2` (when absent), `iso42001` or `eu-ai-act`; must match the type | schema and loader |
| `applies_when` | a mapping of context field to a list of values (risk tier, component scope) | schema and loader |
| `tags` | the control's own key as a tag, for example `cc8.1` or `iso42001:a.6` | loader |

## Rule-declaring concepts

Any concept with `rule_ids`: guardrail policies, scanners, scanner checks ([schema](../src/grc_evidence/data/schemas/concepts/rule-declaring.schema.json))

| Field | Rule | Checked by |
|---|---|---|
| `rule_ids` | `<tool>:<literal prefix>`, optionally ending in `*` | schema and loader |
| `tags` | exactly one control tag per framework | loader |
| `sdks` | the AI SDKs the rules can read | schema and loader |

## Suppressions

`Suppression` ([schema](../src/grc_evidence/data/schemas/concepts/suppression.schema.json))

| Field | Rule | Checked by |
|---|---|---|
| `kind` | `false-positive` or `accepted-risk` | schema and loader |
| `finding` | `tool`, `rule_id` and `target`, exact (no wildcards); optional `message_contains` | schema and loader |
| `owner` | a person: `human:<name>` | schema and loader |
| `approved`, `expires` | `YYYY-MM-DD` | schema and loader |
| `expires` | after `approved`, at most 90 days later | loader |
| body | a non-empty `# Reason` section | loader |
| `kind: accepted-risk` | the finding maps to a control in the bundle | loader |
| `verified` | applied only once a person (`human:`) verified it | mapping |

## Root `index.md`

([schema](../src/grc_evidence/data/schemas/concepts/root-index.schema.json))

| Field | Rule |
|---|---|
| `okf_version` | the OKF version, `"0.2"` |
| `base_version` | the engine release the base copies came from; `grc check` compares it with the installed engine |
