# Reconciliation Contract

Each terminal receipt should preserve workflow and snapshot IDs, workflow/profile key,
config and AI hashes, stable identity, idempotency key, relevant decision reasons,
provider/cost path, approvals, intended destination, external response IDs, side-effect
certainty, readback evidence, terminal outcome, stop reason, and owner. Campaign and
suppression fields are outbound extensions, not universal requirements.
Start from `assets/reconciliation-envelope.schema.json`.

| Write | Required readback |
|---|---|
| Audience upsert | Lookup by stable identity; verify selected fields and no blank regression |
| CRM account/contact update | Lookup returned ID and verify intended fields |
| CRM campaign membership | Lookup exact contact plus campaign pair |
| Sequencer enrollment | Lookup exact email plus campaign and verify required variables |

An API success response is not a readback. Use only terminal outcomes declared in the
workflow contract. A successful mutation outcome such as `synced_verified`,
`routed_verified`, or `activated_verified` requires the intended identifiers, a
non-empty attempt receipt, and independently verified postconditions.

Run `scripts/validate_reconciliation.py` over one receipt or `{ "data": [...] }`.
Two distinct successful mutation receipts for the same idempotency key are a blocker.
A timeout after submission with no resolving readback remains `submitted_unknown`;
reconcile the destination before retrying.
