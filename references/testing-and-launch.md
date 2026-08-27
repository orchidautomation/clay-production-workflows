# Testing and Launch

Use this reference for tests, backfills, publishing, or scale decisions.

## Draft versus live

- Plain/manual tests exercise the current draft.
- Audience-segment tests use the published/live graph after publish.
- Editing or restoring a draft does not publish it.
- Publishing changes the live graph; it does not prove the graph works.

## Bounded ladder

1. One synthetic or approved manual draft record.
2. One real no-write preview.
3. One fully approved end-to-end canary.
4. Two-to-five records covering materially different branches.
5. Ten-to-fifteen records with spend and success stop conditions.
6. Scale only after reconciliation.

State cohort, worst-case credits, BYOA ceiling, permitted/prohibited writes, stop
conditions, approval expiry, and reconciliation owner at each rung.

Before the live rung, verify the incident owner can execute the recorded trigger
pause method and that the rollback snapshot identifies a known-good draft. Restoring
that snapshot is not a live rollback by itself; the restored graph must be audited,
approved, and published.

Derive branch cases from the effective profiles. Always cover success, missing required
input, provider/tool failure, validation failure, review/fallback, and duplicate replay
when those paths exist. Add routing ambiguity and owner-unavailable cases for inbound;
cache hit, stale value, unsupported and exhausted-fallback cases for enrichment; field
stewardship, record-exists, association, timeout-after-submit, and partial-write cases
for CRM; and existing membership, missing email, reply, bounce, unsubscribe, blocklist,
copy rejection, and sequence-mapping cases for outbound.

`completed` may mean enriched, routed, synced, skipped, suppressed, already satisfied,
or review-only. It is supporting evidence, never the business success calculation.
