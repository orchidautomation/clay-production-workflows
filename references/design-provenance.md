# Design Provenance

Maintainer-only source record. Do not load for ordinary workflow work.

## Operational evidence

- Private build transcripts covering parity, bounded credits, Audiences, CRM and
  sequencer writes, missing payload fields, multi-contact flow, and launch gates.
- One finished production workflow and its reusable template, inspected read-only.
- Observed failures including provider HTML/non-JSON responses and sequencer
  blocklist rejection.
- A production audit that exposed a unified-trigger cutover regression, circular
  approval binding, context loss after a destination write, contradictory terminal
  outcomes, label-based write/readback false positives, and a mutable custom
  function outside the workflow snapshot.

No raw transcripts, live workflow identifiers, credentials, private lead values,
customer names, or message bodies are bundled.

## Skill-design sources

Reviewed 2026-08-27:

- [Agent Skills specification](https://agentskills.io/specification): valid frontmatter,
  naming, directory layout, and progressive disclosure.
- [Best practices](https://agentskills.io/skill-creation/best-practices): concise primary
  instructions, focused references, deterministic scripts, and avoid over-generalizing
  one example into a universal rule.
- [Optimizing descriptions](https://agentskills.io/skill-creation/optimizing-descriptions):
  the description is the primary trigger mechanism, so it names positive workflow
  intents and explicit non-workflow exclusions.
- [Evaluating skills](https://agentskills.io/skill-creation/evaluating-skills): train and
  validation query sets contain both should-trigger and should-not-trigger examples.
- [Using scripts](https://agentskills.io/skill-creation/using-scripts): classification,
  evidence collection, and audits are executable and tested instead of relying only
  on prose compliance.

The routing design follows those sources: `SKILL.md` carries the universal kernel and
reference router; capability-specific procedures live in focused profile files; the
classifier supplements declared intent with observed executable behavior; and evals
include non-outbound and compositional workflows to resist example overfitting.
