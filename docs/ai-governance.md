# AI governance

How the bundle covers ISO/IEC 42001 and the EU AI Act, and what it does not claim.

The sample app includes a small LLM feature (`app/assistant/`) seeded with six
AI-governance issues. The bundle maps them to ISO/IEC 42001 Annex A groups and
EU AI Act articles through the same `rule_ids` declarations, keyed
`framework:code` (`iso42001:a.6`, `eu-ai-act:art-50`).

- **Risk-tier applicability** `app/ai-inventory.yaml` declares the EU AI Act
  risk tier (`limited`); it is read from the scan target's `ai-inventory.yaml`, and a
  value other than `minimal`, `limited`, or `high` stops the mapping with an error. Articles that apply only to high-risk systems carry
  `applies_when: {risk_tier: [high]}` and report `not-applicable`, never a gap
  and never `no-violations-detected`. Their findings stay listed.
- **Crosswalks are navigation.** `knowledge/crosswalk/` links related controls
  across frameworks; the report shows each side's own status. A link never
  moves a finding.
- **Honest gaps** Seed AI-6 (AI output written without human review) is
  detected but no control claims its rule, so it is a coverage gap.
- **Clean-room** ISO/IEC 42001 concepts carry clause ids and group names only;
  intents are paraphrased. AI Act articles are paraphrased with EUR-Lex links.
  The OSCAL source for ISO/IEC 42001 is a placeholder: ISO publishes no OSCAL
  catalog.
