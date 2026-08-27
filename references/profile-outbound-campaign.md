# Outbound Campaign Profile

Read this reference when the Workflow generates outreach copy, checks contactability,
or enrolls people into a sequencer.

## Additional invariants

- Define one campaign identity, exact sequence length, target campaign, cohort, and
  approval scope.
- Generator, repair, deterministic validator, QA, payload mapping, and reconciliation
  must agree on every required subject and body field.
- Validate email, person identity, required custom variables, and copy constraints at
  the final payload boundary.
- Check prior membership, replies, bounces, unsubscribes, blocklists, unsafe status,
  and any campaign-specific cooling window that actually applies.
- Repeat time-sensitive suppression immediately before enrollment.
- Separate payload creation, sequencer write, outbound activation, and destination
  verification approvals when those are distinct operations.
- Treat suppression and already-satisfied membership as valid terminal outcomes, not
  technical failures.

Do not apply sequence, suppression, or activation requirements to workflows that do
not generate outreach or enroll a sequencer.
