# Clay Workflow Launch Checklist

Mark each conditional item `PASS`, `BLOCKED`, `UNKNOWN`, or `NOT_APPLICABLE`.

## Applicability

- [ ] Primary profile, composed profiles, and unit of work are declared.
- [ ] Declared capabilities were compared with executable nodes, actions, and triggers.
- [ ] Detected capabilities add safeguards even when the manifest omitted them.
- [ ] Irrelevant profile checks are explicitly `NOT_APPLICABLE`.

## Configuration

- [ ] No placeholders or `REPLACE_ME` values remain.
- [ ] Workflow contract hash matches the approved configuration.
- [ ] Approval is scoped, unexpired, and names an owner.
- [ ] Source identifiers and any destination IDs were verified read-only.
- [ ] When Audience-triggered, entity types and segment counts are correct.
- [ ] When Audience-triggered, one intended trigger generation is active and cohorts do not overlap unexpectedly.
- [ ] Every custom Clay function fingerprint matches the approved manifest.

## Contract

- [ ] Every producer and consumer agrees on each declared cross-node field contract.
- [ ] When outbound, generator, repair, validator, QA, payload, and receipt agree on sequence length.
- [ ] When mutating, all required destination fields are present on every eligible branch.
- [ ] Tool input mappings and result paths were read back after save.
- [ ] Conditional calls, transition registries, targets, and edge handles agree.
- [ ] Context required after a tool node is supplied through explicit input references.
- [ ] Required values are checked at the final decision or payload boundary.

## Safety

- [ ] Worst-case credits and BYOA cost are approved.
- [ ] Routing workflows define precedence, fallback owner/queue, duplicate behavior, and reason codes.
- [ ] Enrichment workflows define cache, freshness, source precedence, usable-value checks, and bounded fallbacks.
- [ ] Outbound workflows define existing membership, reply, bounce, unsubscribe, and blocklist behavior.
- [ ] Outbound workflows repeat time-sensitive suppression immediately before enrollment.
- [ ] Mutations use separate approval gates and an explicit field-stewardship policy.
- [ ] Ambiguous write failures require readback before retry.

## Evidence

- [ ] Manual draft test passed.
- [ ] No-write preview passed.
- [ ] Real canary proved the declared terminal outcome and applicable postconditions.
- [ ] Every intended mutation was independently read back or has documented strongest-available evidence.
- [ ] Duplicate rerun did not duplicate a write, assignment, membership, or work item.
- [ ] Terminal outcome distribution is reported without treating `completed` as success.
- [ ] No later node downgrades a verified side effect or postcondition to false.
- [ ] No run contains incompatible terminal outcome classes.

## Release

- [ ] Published graph is the graph that passed the canary.
- [ ] Live triggers are intentionally bound and paused/resumed as intended.
- [ ] Stop conditions and reconciliation owner are recorded.
- [ ] Business, builder, approver, reconciliation, and incident owners are named.
- [ ] Trigger pause method and known-good rollback snapshot are recorded.
- [ ] Downstream remediation owner understands that graph rollback does not undo writes.
- [ ] Log allowlist, redactions, and evidence/raw-payload retention are recorded.
- [ ] Evidence/CLI compatibility check passed.
