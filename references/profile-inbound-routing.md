# Inbound Routing Profile

Read this reference when the Workflow receives a form, webhook, warehouse event, or
other inbound lead and assigns it to an owner, queue, CRM state, or follow-up path.

## Additional invariants

- Define the routing unit, deduplication key, accepted source contract, and fallback
  owner before assigning records.
- Make precedence explicit when territory, account ownership, named-account rules,
  round robin, capacity, or availability can all claim the same record.
- Prove every eligible branch reaches exactly one accountable owner or a named review
  queue. Never silently drop an unroutable record.
- Preserve the original source receipt and routing reasons for replay and audit.
- Make reassignment, duplicate submission, stale ownership, and owner-unavailable
  behavior explicit.
- Measure routing latency against a declared SLA only when the workflow owns that SLA.
- Verify the final owner or queue in the destination rather than trusting the update
  response alone.

Do not require outbound copy, suppression, or sequencer enrollment unless those
capabilities are also present.
