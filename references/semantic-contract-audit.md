# Semantic Contract Audit

Use this reference for audits, template reviews, and before every publish.

Clay's graph validator checks structural wiring. It can pass while prompts, schemas,
validators, and payloads disagree. One reviewed template required five emails in its
manifest and validator while its generation, repair, and QA agents handled only two.

## Procedure

1. Classify the workflow and mark conditional checks applicable or not applicable.
2. Extract profile, capabilities, unit, cardinalities, required fields, destinations,
   readiness, terminal outcomes, and approvals from the contract.
3. Enumerate every producer and consumer of those fields.
4. Compare names, prompts, schemas, deterministic code, repair, QA, payload mappings, and receipts.
5. Report both sides of each mismatch and the first unsafe effect.
6. Run `scripts/validate_contract.py` only for `copy_sequence`, then inspect fields it marks unknown.
7. Run `scripts/validate_graph_controls.py` with the manifest to check exact
   destination payload requirements, write-to-readback reachability, idempotency,
   suppression, and terminal leaves. Treat unavailable mappings or edges as unknown,
   not as a pass.
8. Run `scripts/validate_snapshot_semantics.py` against the current raw snapshot to
   compare transition calls, configured registries, edge handles, entrypoints, and
   pinned context after tool nodes.
9. Run `scripts/validate_trigger_safety.py` only for `audience_triggered`. Run
   `scripts/analyze_run_traces.py` for all profiles to detect terminal outcomes that
   contradict previously proven side effects.

## Checks

- Sequence length and numbered subject/body fields agree everywhere when outbound.
- Required destination fields are produced on every eligible branch when mutating.
- Output paths use the real tool result shape.
- Tool mappings reference persisted inputs, not invented variables.
- Source and destination IDs match approved values.
- Approval references match and bind to the current config hash.
- Workflow code does not populate its own `approved_config_hash` or approval
  reference from the current unapproved configuration.
- Called conditional transitions, configured transition IDs and targets, and edge
  handles agree exactly; initial adapters do not also receive routed work.
- Retry count is bounded and preserves original context.
- When generation uses QA, QA examines exactly what continues downstream and returns
  verdicts rather than silently changing the contract.
- Readbacks verify the same object and destination context the write targeted.
- A code node that parses a write response is not counted as an independent
  readback; the graph must contain a separate read-only destination action.
- Custom Clay functions are fingerprinted, bound in the manifest, and audited for
  hidden paid work and mutations.
- Audience trigger cohorts do not overlap unless only one generation is proven active.
- A later node never downgrades an already verified write or activation to false or
  reclassifies it as a pre-activation stop.
- Node names do not describe stale behavior that conflicts with prompts or schemas.
- Every approved destination has an inspectable write mapping containing its manifest
  payload fields and a downstream readback.
- Every graph leaf records one recognized terminal outcome.

## Severity

- **BLOCKER**: could spend, write, or send with wrong configuration or incomplete payload.
- **HIGH**: prevents a required path, hides business failure, or breaks reconciliation.
- **MEDIUM**: weakens observability, maintainability, or safe scaling.
- **LOW**: stale naming or hygiene without current execution impact.

Any outbound sequence-cardinality mismatch is a blocker.
