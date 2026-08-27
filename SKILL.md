---
name: clay-production-workflows
description: Build, migrate, explain, visualize, audit, test, and launch-gate multi-node Clay Workflows for enrichment, routing, synchronization, research, and outbound automation. Use for governed workflow architecture, production hardening, parity migrations, reusable templates, bounded canaries, semantic contracts, cost and approval gates, idempotency, external-write verification, and downstream reconciliation. Do not use for simple table explanations, one-off enrichment questions, generic non-Clay diagrams, or read-only audience counts.
license: MIT
compatibility: Python 3.11+ for offline checks; authenticated Clay CLI and network access for live evidence collection.
metadata:
  author: orchid-automation
  version: "0.8.0"
---

# Clay Production Workflows

Treat a Clay Workflow as a governed production system, not merely a valid graph.
The target outcome is a workflow whose configuration, contracts, test evidence,
external writes, and readbacks agree.

## Applicability before procedure

First classify the workflow's business purpose and capabilities. Read
[applicability-and-profiles.md](references/applicability-and-profiles.md) for every
build, migration, audit, or launch-gate task. Apply the universal production kernel
to every in-scope workflow, then load only the profile references whose capabilities
are present:

- Routing or assignment: [profile-inbound-routing.md](references/profile-inbound-routing.md)
- Paid enrichment, normalization, or research: [profile-enrichment-sync.md](references/profile-enrichment-sync.md)
- CRM creation, update, ownership, or membership: [profile-crm-sync.md](references/profile-crm-sync.md)
- Copy sequences or sequencer activation: [profile-outbound-campaign.md](references/profile-outbound-campaign.md)
- Audience triggers or Audience writes: [profile-audience-triggered.md](references/profile-audience-triggered.md)

Profiles compose. Do not require copy, suppression, CRM, sequencer, or Audience
controls when the corresponding capability is absent. Report an irrelevant check as
`NOT_APPLICABLE`; report an applicable check without evidence as `UNKNOWN` or
`NOT_CHECKED`. A workflow-specific convention becomes universal only when it protects
a general safety invariant.

## Requirements

The offline scripts require Python 3.11+. Live evidence collection additionally
requires the Clay CLI supplied by the Clay plugin, authenticated workspace access,
and network access. Fixture analysis and semantic checks work without Clay access.

## Boundaries

- Use this skill for Clay **Workflows** or a table-driven flow being moved into a
  governed Workflow.
- For explaining an existing Clay table DAG, use the Clay table-analysis workflow.
- For ordinary Audience counts or filters, use the Clay Audiences workflow.
- Never run paid enrichments, tests, backfills, publish, resume triggers, or write
  to Audiences, CRM, or a sequencer without the user's explicit approval for that
  action and scope.
- A request to audit or design does not authorize mutation.

## Pair with the Clay plugin

When the Clay plugin is available, use its `clay` entry-point skill to select the
right product surface and its focused skills for live mechanics. This skill does
not replace those instructions: it adds production contracts, approvals, evidence,
and launch criteria around multi-node Workflows.

For builds and edits, use the plugin's workflow skills to discover current actions
and schemas, mutate the graph, validate structure, inspect runs, manage snapshots,
and distinguish draft from published behavior. Apply this skill before graph work
to define the canonical contract, during the build to preserve its invariants, and
afterward to audit semantics, bound testing, reconcile writes, and issue readiness.

Read [clay-plugin-integration.md](references/clay-plugin-integration.md) when routing
a mixed Clay request, combining plugin skills during a production Workflow task, or
deciding which layer owns a check. If the plugin is absent, keep using offline
fixtures and semantic checks; do not invent live CLI shapes or claim workspace proof.

## Choose the operating mode

1. **Audit an existing workflow** — collect read-only evidence, validate the graph,
   run the semantic contract audit, inspect run outcomes, and issue a readiness
   ceiling. Read [semantic-contract-audit.md](references/semantic-contract-audit.md)
   and [failure-taxonomy.md](references/failure-taxonomy.md). When launch or live
   operation is in scope, also read [operations-and-data.md](references/operations-and-data.md).
2. **Build or migrate for parity** — define the canonical contract, stage the
   architecture, add fail-closed controls, and prove parity with bounded evidence.
   Read [architecture.md](references/architecture.md).
3. **Instantiate a reusable template** — replace the workflow contract and applicable
   profile extensions, rebind safe sources and destinations, invalidate stale
   approvals, and test all contract
   consumers. Read [template-instantiation.md](references/template-instantiation.md).
4. **Test or launch-gate** — use the bounded ladder, distinguish draft from live,
   reconcile every write, and report a readiness verdict. Read
   [testing-and-launch.md](references/testing-and-launch.md) and
   [reconciliation.md](references/reconciliation.md).
5. **Explain in plain English** — turn the graph and available run evidence into a
   noob-friendly operating story without mistaking labels for enforced behavior.
   Read [plain-english-explainer.md](references/plain-english-explainer.md).
6. **Visualize a supplied workflow diagram** — turn a Mermaid flowchart for a Clay
   production workflow into a faithful in-conversation visual without dropping
   gates, stop paths, stage boundaries, or evidence caveats. Read
   [workflow-visualization.md](references/workflow-visualization.md).

## Read-only evidence collection

Confirm the Clay workspace once with `clay whoami`. Share the workflow link and
human-readable name. Then prefer the bundled collector over repeated ad hoc commands:

```bash
python3 scripts/collect_workflow_evidence.py WORKFLOW_ID --output EVIDENCE_DIR \
  --manifest workflow-contract.json --receipts reconciliation-receipts.json \
  --trace-run BOUNDED_CANARY_RUN_ID
```

The collector only reads workflow metadata, graph, validation, the current raw
snapshot, triggers, redacted Audience cohort fingerprints, custom-function
fingerprints, and recent run metadata. `--trace-run` adds an allowlisted outcome
trace without emails, message bodies, or raw provider payloads. It does not test,
publish, resume, or mutate.

Audit the evidence:

```bash
python3 scripts/classify_workflow.py EVIDENCE_DIR/graph.json \
  --manifest EVIDENCE_DIR/manifest.json --triggers EVIDENCE_DIR/triggers.json
python3 scripts/validate_contract.py EVIDENCE_DIR/graph.json \
  --validation EVIDENCE_DIR/validation.json
python3 scripts/validate_manifest.py EVIDENCE_DIR/manifest.json
python3 scripts/validate_graph_controls.py EVIDENCE_DIR/graph.json \
  --manifest EVIDENCE_DIR/manifest.json \
  --function-fingerprints EVIDENCE_DIR/function-fingerprints.json
python3 scripts/validate_snapshot_semantics.py EVIDENCE_DIR/current-snapshot.json
python3 scripts/validate_trigger_safety.py EVIDENCE_DIR/triggers.json \
  --audience-segments EVIDENCE_DIR/audience-segments.json
python3 scripts/analyze_run_traces.py EVIDENCE_DIR/run-traces.json
python3 scripts/check_evidence_compat.py EVIDENCE_DIR
python3 scripts/validate_reconciliation.py EVIDENCE_DIR/receipts.json \
  --manifest EVIDENCE_DIR/manifest.json
python3 scripts/summarize_runs.py EVIDENCE_DIR/runs.json \
  --failed-runs EVIDENCE_DIR/failed-runs.json --graph EVIDENCE_DIR/graph.json
python3 scripts/audit_workflow.py EVIDENCE_DIR
```

The classifier and aggregate audit determine applicability. Run sequence, trigger,
or reconciliation validators individually only when their reported capability is
present; the aggregate audit records irrelevant checks as `NOT_APPLICABLE`.

Explain the workflow for a non-technical reader:

```bash
python3 scripts/explain_workflow.py EVIDENCE_DIR --audience general
```

When the user supplies Mermaid and asks to see the workflow as a visualization in
the conversation, treat the Mermaid as the source diagram and follow
[workflow-visualization.md](references/workflow-visualization.md). Use the host's
native in-conversation visualization capability when it is available. Do not turn
that request into a standalone website or silently return the same Mermaid source.

Read [script-contracts.md](references/script-contracts.md) before modifying or
replacing these scripts. Structured data goes to stdout; diagnostics go to stderr.

## Canonical contract before graph work

Define one workflow contract covering profile, capabilities, lifecycle state, unit of
work, sources, required fields, stable identity, terminal outcomes, worst-case cost,
approval scope, accountable owners, kill switch, rollback, data handling, and mutable
dependencies. Add destination payloads and verification for every external mutation.
Add campaign identity, exact sequence length, suppression, and activation only for
outbound workflows.

Start from [workflow-contract.template.json](assets/workflow-contract.template.json).
Extend it with [campaign-manifest.template.json](assets/campaign-manifest.template.json)
only for outbound campaigns. Defaults must permit no paid work, publish, or external
writes. Changing the normalized manifest must invalidate prior approval.

The normalized configuration excludes the `approvals` object so approval evidence
does not create a circular hash. Use the hash reported by
`scripts/validate_manifest.py`; never hand-edit or approximate it. A production
claim requires named business, build, approval, reconciliation, and incident owners.

## Production architecture

Assemble only the stages the effective capabilities require: safe entry adapter;
fail-closed preflight; deterministic routing or eligibility; cache-aware enrichment;
durable work items where independent retry is required; deterministic validation;
payload preview; separately approved mutations; and postcondition verification.
Copy generation, repair, QA, suppression, and sequencer activation belong only to the
outbound profile.

Use deterministic code for routing, normalization, validation, hashing, budgets,
and identifiers. Use agents only for judgment or generation. Preserve exact values
with typed schemas or explicit tool input mappings.

Treat a write response as an attempt receipt, not proof of the postcondition. Prefer
a separate destination read. When the provider has no read surface, require the
strongest independent evidence available—such as a correlated webhook, transactional
receipt, or downstream query—and state the residual uncertainty.

## Mandatory semantic audit

Clay graph validation is necessary but not sufficient. Compare the canonical
contract across node names, prompts, input/output schemas, validators, repair
agents, QA agents, payload builders, destination mappings, and receipts.

For an outbound sequence of length `N`, every consumer must produce, validate, map,
and reconcile exactly `N` subjects and bodies. For other profiles, identify the
equivalent cross-node contract: routing owner and reason, enriched fields and
evidence, CRM object and stewardship, or declared payload and postcondition. A
structural pass cannot override a semantic mismatch. Treat an untested template as
unproven even when it validates.

## Identity, idempotency, and conditional suppression

- Validate actual required values, not just successful node statuses.
- Choose stable identity appropriate to the unit of work. For people and companies,
  normalized LinkedIn URL, domain, and durable CRM IDs are common options.
- Derive idempotency from workflow purpose plus stable unit identity.
- Declare field stewardship; fill-only is a safe default for enrichment sync, not a
  universal overwrite policy.
- Apply campaign membership, reply, bounce, unsubscribe, blocklist, and just-in-time
  suppression checks only when outbound activation is present.

## Testing and readiness

Progress through one manual draft record, one no-write preview, one approved canary,
two-to-five branch-covering records, then a bounded cohort with a stop condition.
Scale only after destination readbacks are verified.

Do not equate Clay `completed` with business success. Declare terminal outcomes for
the profile and include verified success, already satisfied or safely skipped,
review/fallback, provider failure, destination rejection when applicable, and
reconciliation failure when mutation is possible.

Use only `DRAFT_BLOCKED`, `PREVIEW_READY`, `CANARY_READY`, or `LIVE_READY`.
`LIVE_READY` requires a real canary that proved the declared terminal outcome and all
applicable postconditions. External mutations require independent destination
readback; all workflows require an outcome trace with no side-effect downgrade or
contradictory terminal classification. Static inspection can set a ceiling but cannot
prove it.

Before live operation, record the exact trigger pause method, rollback snapshot,
downstream remediation owner, permitted log fields, redactions, and retention. A
snapshot restore changes the draft only; it is not a live rollback until the
restored graph is re-audited, approved, and published. See
[operations-and-data.md](references/operations-and-data.md).

## Failure handling

Recognize non-JSON/HTML provider responses, rate limits, timeouts, blocklists,
validation errors, stale destination IDs, missing credentials, and partial writes.
Do not blindly retry an external mutation. First determine whether it landed.
If Clay terminates before reconciliation, report side-effect uncertainty and the
exact readback required. See [failure-taxonomy.md](references/failure-taxonomy.md).

## Report

Use [workflow-audit-report.template.md](assets/workflow-audit-report.template.md).
Include the workflow link, compact graph, structural and semantic findings, trigger
safety, test evidence, outcome limits, costs and approvals, downstream readbacks,
readiness verdict, and exact remaining actions. Summarize evidence; do not dump raw
graphs, private records, credentials, or message bodies.

When the user asks what the workflow does, write a connected story before any
inventory, table, or checklist. Give the record a concrete role in the narrative and
walk it from entry to terminal outcome using transitions that explain why each stage
exists. Do not substitute numbered phase summaries for prose. Separate three evidence layers:
what node labels and descriptions say is intended, what executable configuration
enforces, and what runs plus destination readbacks prove happened. Define unfamiliar
Clay and GTM terms at first use. Name paid steps, approval gates, external writes,
suppression paths, failure paths, and what remains unknown. Start from
[workflow-explainer.template.md](assets/workflow-explainer.template.md) when a durable
explanation artifact is useful.

Do not paraphrase an executable filter as merely “checks fit,” “checks eligibility,”
or “checks safety.” Preserve the exact field names, normalized keys, configured values,
include/exclude terms, comparison operators, accepted statuses, tool mappings, and
payload requirements that make the branch pass or fail. Put field names in backticks
and explain their business meaning in the same paragraph.

## Provenance

The non-obvious rules come from real Clay build transcripts, a finished production
workflow, its reusable template, and observed failures. Read
[design-provenance.md](references/design-provenance.md) only when maintaining the
skill or evaluating whether a rule is still justified.
