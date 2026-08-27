# CRM Synchronization Profile

Read this reference when the Workflow creates or updates CRM accounts, contacts,
leads, deals, campaign membership, ownership, or other CRM state.

## Additional invariants

- Resolve the target object and stable identity before mutation; avoid email-only
  identity when a durable CRM ID is available.
- Declare field stewardship and overwrite policy per field. Fill-only is a safe
  default, not a universal rule.
- Separate record creation, record update, association or membership, and ownership
  changes when they have different approvals or rollback consequences.
- Use an idempotency key or read-before-create policy that survives reruns.
- Verify exact object IDs, associations, ownership, and material field equality after
  mutation using the strongest available CRM read surface.
- On timeout after submission, read the CRM before retrying.
- Preserve partial success explicitly when one object or association lands and another
  fails.

Provider-specific Salesforce or HubSpot fields belong in the workflow manifest or
payload contract, not in the universal skill kernel.
