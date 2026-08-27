# Template Instantiation

1. Duplicate the template and preserve source workflow/snapshot identifiers.
2. Classify the target purpose and capabilities; load only applicable profiles.
3. Keep triggers disabled or on empty control inputs while configuring.
4. Replace placeholders, sources, destinations, owner, counts, and budgets.
5. Set state to `DRAFT` and all approvals false.
6. Normalize and hash the manifest.
7. Rebind input sources; verify source contract, entity, and count.
8. Resolve destinations through read-only lookups when mutations are present.
9. Run the semantic audit across every producer and consumer of each declared field.
10. Update outdated agents and re-read persisted prompts/schemas when agents are present.
11. Run a no-write preview before paid-work or mutation approval.
12. Bind approval to final manifest hash, approver, timestamp, scope, and expiry.
13. Follow the bounded ladder.

Before approval, name all five production owners, record the trigger pause method and
known-good rollback snapshot, and set the log allowlist, redactions, and retention.
Use the hash emitted by `scripts/validate_manifest.py`; approval fields are excluded
from normalization so the approval evidence does not hash itself.

Changing any cross-node contract requires updating every producer and consumer. For
outbound, that includes generator, repair, validator, QA, payload, destination
variables, and receipts. A structurally valid, untested template is unproven.
