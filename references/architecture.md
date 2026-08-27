# Governed Workflow Architecture

Use this reference when building a new Clay Workflow or migrating an existing table
or workbook for parity.

## Composable stage contract

Select stages from the effective capabilities; this is not a required linear recipe.

| Stage | When applicable | Responsibility | Proof before proceeding |
|---|---|---|---|
| Entry adapter | Always | Normalize Audience, manual, schedule, webhook, or queue input | Canonical unit and source receipt |
| Preflight | Always | Bind contract, approvals, counts, budgets, and dependencies | Config hash, source verification, readiness state |
| Decision | Eligibility or routing | Apply deterministic filters, assignment precedence, and fallbacks | Verdict, reason, and accountable next owner |
| Enrichment | Paid or cached research | Use valid existing/cache values before approved paid paths | Provider, cost, usable value, and validation state |
| Durable queue | Independent retry or fan-out | Create one replayable work item per unit | Expected count, stable identity, idempotency key, queue receipt |
| Generation | Judgment or copy creation | Produce only declared typed fields | Schema-valid result and bounded attempts |
| Validation | Always | Enforce deterministic cross-node and final-boundary rules | Violations, retry count, and explicit disposition |
| Suppression | Outbound only | Detect unsafe or already-satisfied contact state | Lookup status, reason, and freshness |
| Preview | External mutation | Assemble the exact destination payload | Missing-field list and destination binding |
| Mutation | External mutation | Perform one separately approved write | Attempt receipt and approval reference |
| Reconciliation | External mutation | Verify the destination postcondition | Exact identifiers, material field match, terminal receipt |

## Design invariants

- One workflow contract is the governed edit surface; profile extensions hold
  campaign, routing, enrichment, CRM, or Audience-specific details.
- Safe templates point at empty control segments and placeholder destinations.
- Entry adapters normalize; the manifest decides eligibility.
- Paid tools come after deterministic filters and cache checks.
- Fan-out becomes durable per-unit work when independent retries, receipts, or
  downstream side effects are required.
- Every external mutation has a preceding gate and a following readback.
- Every branch reaches a named terminal outcome; skip, review, and failure are explicit.
- Context passed to AI is compact, signed, and distinct from the operational receipt.
- Production ownership, kill-switch controls, rollback evidence, and retention are
  part of the contract rather than launch-day notes.

## Parity matrix

Compare the universal kernel plus every applicable profile: sources, decisions,
providers and fallbacks, required fields, field stewardship, costs, failures,
destinations, and reconciliation. Compare copy, suppression, Audience, CRM, routing,
or sequencer behavior only when present. Visual similarity or one happy-path record
is not parity.
