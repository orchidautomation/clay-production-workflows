# Production Operations and Data Handling

Use this reference before publishing, enabling triggers, scaling a cohort, or
responding to a live incident.

## Accountable owners

The manifest names five roles. One person may hold more than one role, but every
responsibility must be explicit:

| Role | Decision or duty |
|---|---|
| Business owner | Owns eligibility, messaging intent, destinations, and acceptable business outcomes |
| Builder | Owns graph configuration, mappings, deterministic checks, and evidence collection |
| Approver | Authorizes the exact normalized configuration, cohort, spend, writes, and expiry |
| Reconciliation owner | Verifies destinations and resolves ambiguous or partial writes |
| Incident owner | Can stop live work, coordinate rollback, and own downstream remediation |

Do not infer an owner from the workflow creator or connected-account holder. A
production claim with a missing owner is not launch-ready.

## Trigger cutovers

Treat replacement of batch triggers with a unified trigger as a release migration.
Hash stable cohort identities, compare the old and new segment generations, and
prove which trigger IDs are active, paused, or unpublished. Overlapping cohorts are
release-blocking when both generations are active and remain high risk when trigger
state is unavailable. Do not leave both generations enabled as a fallback.

## Kill switch and rollback

Record the live trigger IDs, exact pause or disable method, incident owner, known-good
snapshot ID, and downstream remediation owner before activation. Test the pause
procedure without sending or mutating when the platform permits a safe check.

On an incident:

1. Stop new work using the recorded trigger control.
2. Preserve the current workflow, run, and destination evidence.
3. Reconcile writes whose side effects are uncertain before retrying or compensating.
4. Restore the draft only after comparing the current graph with the target snapshot.
5. Re-audit the restored configuration. Snapshot restore does not change the live
   published graph.
6. Publish only with explicit approval, then run a bounded verification record.
7. Remediate downstream records through the named owner; never assume graph rollback
   reverses CRM, Audience, or sequencer mutations.

## Data classification and retention

Treat person and account enrichment data, outbound copy, provider payloads, and
destination receipts as confidential unless the organization has classified them
otherwise. Credentials and secrets must never enter evidence bundles or reports.

The manifest records:

- fields permitted in ordinary logs;
- fields that must be redacted;
- evidence retention in days;
- raw provider-payload retention in days.

Prefer identifiers, hashes, counts, statuses, error classes, and short redacted
excerpts over full records. Store raw payloads only when required for a bounded
diagnostic purpose, assign an owner, and delete them at the configured deadline.
Do not retain message bodies, credentials, or private record values merely because
they appeared in a run response.

## Compatibility gate

The evidence collector records an evidence-contract version, a redaction receipt,
and the observed Clay CLI version. Run `scripts/check_evidence_compat.py` before
trusting an audit. A changed or missing required JSON shape blocks automated
conclusions until the collector/parser is updated. A v1 bundle remains readable,
but raw-snapshot, trigger-overlap, custom-function, and run-trace coverage must be
reported as unavailable rather than passed.
