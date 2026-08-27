# Clay Plugin Integration

Use this reference when the Clay plugin and this production skill are both
available. The plugin is the live operational layer; this skill is the production
assurance layer. They should cooperate without copying each other's manuals.

## Responsibility split

| Need | Owning layer |
|---|---|
| Choose Audiences, Search, Routines, Tables, or Workflows | Clay plugin entry point |
| Read existing Audience records or segments | Clay Audiences skill |
| Find net-new people or companies | Clay Search skill |
| Run an existing function or Workflow over inputs | Clay Routines skill |
| Explain or diagnose an existing table | Focused Clay Tables skill |
| Discover current actions, schemas, costs, and connected accounts | Clay workflow action-discovery skill |
| Create or edit nodes, triggers, edges, code, and tool mappings | Clay workflow CLI skill |
| Compare or restore draft history | Clay workflow snapshots skill |
| Classify capabilities and define workflow contract, approvals, idempotency, and terminal outcomes | This skill |
| Audit semantic agreement across producers and consumers | This skill |
| Design bounded canaries and readiness ceilings | This skill |
| Reconcile Audience, CRM, or sequencer writes | This skill, using available read surfaces |

Do not route an ordinary Audience count, Search, routine run, or table diagnosis
through production governance. Add this skill when a multi-node Workflow can spend
materially, mutate another system, activate outreach, run unattended, or scale.

## Combined operating sequence

1. Start with the plugin entry point. Prefer existing Audience data and existing
   routines before proposing net-new search, enrichment, or a Workflow.
2. Confirm the authenticated workspace once. Resolve the human-readable Workflow
   name and link before discussing identifiers.
3. For a production Workflow, classify its capabilities and define or recover the
   canonical workflow contract before editing the graph. Read-only inspection does
   not authorize mutation.
4. Use the plugin's action catalog and schemas instead of guessing action keys,
   result paths, credit costs, account bindings, or writable node shapes.
5. Use the plugin's workflow CLI guidance for the actual graph operations. Re-read
   persisted nodes after consequential edits; a successful update response is not
   semantic proof.
6. Run Clay structural validation, then this skill's semantic audit. Structural
   validity cannot override a contract mismatch.
7. Use the plugin's draft, publish, test, and snapshot rules while following this
   skill's bounded ladder. Approval for one rung does not authorize the next.
8. After each approved external write, use the strongest available destination
   lookup to reconcile the exact record and campaign. A Clay run status or write
   response alone is not a readback.

## Shared approval rule

The plugin requires explicit approval before credit-consuming actions. This skill
extends that boundary by binding approval to the normalized workflow configuration,
record cohort, worst-case spend, permitted destinations, write types, stop
conditions, and expiry. Satisfy both layers before acting.

If the user approves a routine or test without approving an external mutation,
keep downstream writes disabled. A request to audit, design, estimate, explain, or
"run the remaining audience" is not approval to publish, resume triggers, backfill,
enroll, or scale.

## Important handoffs

- A table is full, erroring, or contains a surprising cell: use the focused Tables
  diagnosis first. Migrate to a governed Workflow only when the user actually wants
  a repeatable production replacement.
- A workflow is structurally broken: repair it with the workflow CLI guidance, then
  rerun the semantic audit rather than declaring readiness from validation alone.
- An optimization or simplification changes nodes, prompts, models, providers,
  branching, or mappings: treat it as a contract change. Recompute cost, invalidate
  stale approval when normalized configuration changed, and repeat affected tests.
- A snapshot restore changes the draft only. It neither republishes the graph nor
  proves that the restored version is safe. Re-audit and explicitly publish only
  after approval.
- A run fails after an external request may have been submitted: do not blindly
  retry through either layer. Read the destination first and classify side-effect
  certainty.

## Evidence language

Keep the layers explicit in team updates:

- **Plugin evidence:** current workspace identity, live schemas, graph structure,
  validation results, snapshots, run metadata, and action costs.
- **Production evidence:** contract agreement, approval binding, branch coverage,
  terminal outcome classification, idempotency behavior, and destination readbacks.

State what is configured, what was tested, and what was independently verified.
Only the last category can support `LIVE_READY`.
