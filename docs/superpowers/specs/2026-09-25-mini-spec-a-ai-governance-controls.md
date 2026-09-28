# Mini Spec A — AI Governance Controls (ISO/IEC 42001 + EU AI Act)

- **Date:** 2026-09-25
- **Status:** draft, for review
- **Depends on:** v1 (`2026-09-25-okf-grc-skill-v1-design.md`)
- **LLM cost:** none. The scan stays deterministic.

## 1. Why

AI-lab GRC roles now name ISO/IEC 42001 and the EU AI Act (Cursor, xAI, Replit).
v1 covers SOC 2 and NIST 800-53 only. This spec adds an AI-system layer to the
sample app and a second framework family to the bundle. The grounding rule does
not change.

## 2. Goal and definition of done

The scan finds seeded AI-governance issues in `app/`. It maps each one to an
ISO 42001 Annex A control and to an EU AI Act article through `rule_ids` only.

**Done when:**

1. `make scan` reports each new seeded AI issue against its expected control.
2. One seeded AI issue has no rule declaration. It appears as a coverage gap.
3. Controls that do not apply to the declared risk tier show `not-applicable`.
   They never show as a gap or as `no-violations-detected`.
4. The report has one section per framework and a crosswalk table.
5. OSCAL output validates. It has one `control-implementation` per framework source.
6. `make test` and `make test-integration` pass.

**Out of scope:** conformity assessment, a real risk classification service,
model evaluation, NIST AI RMF as a third framework (crosswalk links only).

## 3. Clean-room rules

- ISO/IEC 42001 text is copyrighted. Use clause IDs and group names only.
  Write each intent in your own words. Do not paste Annex A text.
- Verify every Annex A clause ID against a licensed copy before you mark a
  concept `verified`.
- The EU AI Act (Regulation (EU) 2024/1689) is public law. Cite article numbers.
  Paraphrase, and link to the EUR-Lex text.
- NIST AI RMF is public. Use it for crosswalk links only.

## 4. Sample app changes (`app/`)

Add one small AI feature: `app/assistant/`. It is a DRF view that sends a
widget description to an LLM and returns a summary. It is never run.

Seed these issues and add each one to `app/SEEDED.yaml`:

| Seed ID | Issue | Expected mapping |
|---|---|---|
| AI-1 | The prompt and the user input are written to the log in clear text | 42001 A.7 (data for AI systems); AI Act Art. 10, Art. 12 |
| AI-2 | The API key is hard-coded in `settings.py` | SOC 2 CC6.1 (existing) + 42001 A.6 |
| AI-3 | The LLM call has no timeout and no `max_tokens` bound | 42001 A.6 (life cycle, operation) ; AI Act Art. 15 |
| AI-4 | The response does not tell the user that AI made it | AI Act Art. 50 (transparency) |
| AI-5 | `ai-inventory.yaml` has no entry for the assistant feature | 42001 A.4 (resources) / A.6 |
| AI-6 | No human-review flag on a write path that uses AI output | **Coverage gap** (no rule declared) |

## 5. Bundle changes (`knowledge/`)

New concept types and folders:

```
knowledge/
├── controls/iso42001/   a.4.md a.5.md a.6.md a.7.md a.8.md a.9.md
├── controls/eu-ai-act/  art-9.md art-10.md art-12.md art-13.md art-14.md art-15.md art-50.md
├── crosswalk/           soc2-iso42001.md  iso42001-ai-act.md  (links, no mapping logic)
├── stack/ai-assistant.md
└── ai-inventory.md      describes the inventory file and the declared risk tier
```

Control concept frontmatter adds two fields:

```yaml
framework: iso42001        # soc2 | iso42001 | eu-ai-act
applies_when:              # optional; omitted = always applies
  risk_tier: [high]        # read from app/ai-inventory.yaml
```

- The sample app declares `risk_tier: limited`. So Art. 9–15 (high-risk
  obligations) are `not-applicable`. Art. 50 applies. This shows the
  applicability logic in the report.
- **Note for the design review:** AI-3 maps to Art. 15. Art. 15 is a high-risk
  article. Decide one of these: (a) raise the sample tier to `high` for a second
  fixture, or (b) keep AI-3 on 42001 only. Recommendation: (b), plus a unit test
  fixture at `high`.

## 6. Rules and scanners

No new scanner. Reuse Semgrep and Conftest.

| Rule | Tool | Finds |
|---|---|---|
| `semgrep:llm-prompt-logged` | Semgrep | a logger call with a prompt or completion variable |
| `semgrep:llm-hardcoded-key` | Semgrep | a string literal assigned to an `*_API_KEY` name |
| `semgrep:llm-unbounded-call` | Semgrep | an LLM client call with no `timeout` or no `max_tokens` |
| `semgrep:llm-no-ai-disclosure` | Semgrep | a view returns model output with no disclosure field |
| `conftest:ai-inventory-complete` | Conftest (Rego) | an `assistant`-type module with no inventory entry |

Each rule gets a Semgrep test file or a Rego `_test.rego` file, as in v1.

## 7. Code changes

- `okf_lib.py`: read `framework` and `applies_when`. Key controls by
  `framework:code`, for example `iso42001:a.6`.
- `map_findings.py`: add status `not-applicable`. Set it before the finding
  loop, from `applies_when` and `app/ai-inventory.yaml`. A finding on a
  `not-applicable` control stays listed but does not change the status. Record
  the reason `control-not-applicable`.
- `to_oscal.py`: one `control-implementation` per framework `source`. Use a
  clean-room placeholder source URI for ISO 42001 (no official OSCAL catalog).
  Document this in `docs/oscal-subset.md`.
- `render_report.py`: group sections by framework. Add the crosswalk table.

## 8. Tests

- Unit: `applies_when` logic (limited vs. high fixture), multi-framework keys,
  `not-applicable` status, crosswalk links resolve.
- Integration: every AI seed lands where `SEEDED.yaml` says. AI-6 is a gap.
- Conformance: every new concept has `framework`, `generated`, and links that
  resolve.

## 9. Tasks (estimate: 3–4 focused days)

1. Add `framework` field and multi-framework keys. Keep all v1 tests green.
2. Add `not-applicable` status and `applies_when`.
3. Write `app/assistant/` and `app/ai-inventory.yaml` with seeds AI-1..AI-6.
4. Write the 5 rules with tests.
5. Write the control, crosswalk, and stack concepts. Human review pass.
6. OSCAL multi-source output and schema validation.
7. Report sections and crosswalk. Refresh `examples/report.md` and screenshots.
8. README: add the AI governance paragraph and a new "Limits" line.

## 10. Resume line when done

> Extended an OKF-grounded GRC agent to ISO/IEC 42001 and the EU AI Act:
> risk-tier applicability, multi-framework OSCAL, and enforced grounding
> (unmapped AI findings surface as coverage gaps).
