# Applicability and Workflow Profiles

Read this reference first for every build, audit, migration, or launch-gate request.
It prevents a rule learned from one workflow type from becoming an irrelevant
requirement for another.

## Decision order

1. Identify the user's intended business outcome and unit of work.
2. Inspect executable nodes, actions, triggers, and destinations.
3. Declare or recover the primary profile and capabilities.
4. Apply the universal kernel to every production workflow.
5. Load only the references matching the effective capabilities.
6. Mark irrelevant checks `NOT_APPLICABLE`; mark relevant checks without evidence
   `UNKNOWN` or `NOT_CHECKED`. Never turn absence of an irrelevant feature into a
   failure.

Run `scripts/classify_workflow.py` when graph evidence is available. A declared
profile is authoritative for intent; detected capabilities supplement it and expose
manifest drift. Inference routes the audit but must not invent user authorization or
business intent.

## Universal production kernel

Apply these invariants whenever a multi-node Clay Workflow can spend materially,
mutate state, run unattended, or scale:

- Separate intended labels, executable configuration, and observed runtime proof.
- Structural validation cannot override a semantic contract mismatch.
- `completed` proves technical termination, not the business outcome.
- Bind paid work, mutation, publishing, testing, and scale to explicit scoped approval.
- Calculate worst-case cost and bounded cohort size before execution.
- Preserve required context and typed field contracts across every node boundary.
- Give each durable unit of work a stable identity and idempotency policy.
- Treat a write response as an attempt receipt; require independent postcondition
  evidence appropriate to the destination before claiming success or retrying.
- Fingerprint mutable dependencies that are not contained by the Workflow snapshot.
- Use bounded tests, explicit stop conditions, incident ownership, and rollback plans.
- Report evidence coverage explicitly; missing evidence is never a silent pass.

## Capability routing

| Capability | Signals | Additional rules |
|---|---|---|
| `routing` | Conditional assignment, owner, territory, queue, or SLA branches | Read [profile-inbound-routing.md](profile-inbound-routing.md) when routing is the business purpose. |
| `paid_enrichment` | Paid/enrichment actions, Claygent, waterfalls, email finders | Read [profile-enrichment-sync.md](profile-enrichment-sync.md). |
| `external_mutation` | Create, update, upsert, enroll, send, or generic write action | Require idempotency and postcondition verification. |
| `crm_sync` | Salesforce, HubSpot, or another declared CRM mutation | Read [profile-crm-sync.md](profile-crm-sync.md). |
| `copy_sequence` or `sequencer_activation` | Numbered subjects/bodies, sequencer mapping, enrollment | Read [profile-outbound-campaign.md](profile-outbound-campaign.md). |
| `audience_triggered` or `audience_sync` | Audience segment trigger or Audience mutation | Read [profile-audience-triggered.md](profile-audience-triggered.md). |
| `custom_functions` | Referenced Clay custom/workspace function | Fingerprint and bind the function to the approved manifest. |

Profiles can compose. An Audience-triggered outbound campaign that enriches people,
syncs Salesforce, and enrolls a sequencer should load all relevant profiles. A
read-only enrichment workflow should not inherit suppression, sequence, CRM-write,
or trigger-cutover requirements.

## Evidence language

- `PROVEN`: evidence directly establishes the check.
- `FAILED`: relevant evidence contradicts the required invariant.
- `UNKNOWN`: the check applies but the available surface cannot establish it.
- `NOT_CHECKED`: the check applies but evidence was not collected.
- `NOT_APPLICABLE`: the capability is absent, so the check is intentionally skipped.

Only `FAILED` blocks because of a demonstrated defect. `UNKNOWN` and `NOT_CHECKED`
limit the readiness ceiling because proof is missing. `NOT_APPLICABLE` does neither.
