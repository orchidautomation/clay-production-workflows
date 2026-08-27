# Audience Integration Profile

Read this reference when a Clay Audience segment starts the Workflow or when the
Workflow reads from or writes to an Audience.

## Additional invariants

- Record the exact segment ID, entity type, count, and observation time used for a
  bounded run.
- Treat replacement of legacy segments or triggers as a release migration.
- Compare old and new cohorts using redacted stable identities when possible.
- Prove which trigger generation is active, paused, draft, or unknown before launch.
- Overlap blocks launch when two generations are active; unknown activation state
  limits readiness until verified.
- Verify Audience writes by stable record identity and the material fields claimed by
  the workflow.
- Keep empty control segments in reusable templates until a real source is explicitly
  rebound and approved.

These rules do not apply to manual, scheduled, webhook, or other triggers unless an
Audience segment is also part of the execution path.
